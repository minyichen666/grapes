from typing import Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv, GCN2Conv, GCNConv, Linear,  PNAConv
from torch_geometric.nn import SAGEConv

class GraphSAGE(nn.Module):
    def __init__(self, in_features: int, hidden_dims: list[int], dropout: float=0.):
        super(GraphSAGE, self).__init__()
        self.dropout = dropout
        dims = [in_features] + hidden_dims
        sage_layers = []
        for i in range(len(hidden_dims) - 1):
            sage_layers.append(SAGEConv(in_channels=dims[i], out_channels=dims[i + 1]))

        sage_layers.append(SAGEConv(in_channels=dims[-2], out_channels=dims[-1]))
        self.sage_layers = nn.ModuleList(sage_layers)

    def forward(self, x: torch.Tensor, edge_index: Union[torch.Tensor, list[torch.Tensor]]) -> torch.Tensor:
        layerwise_adjacency = isinstance(edge_index, list)

        for i, layer in enumerate(self.sage_layers[:-1], start=1):
            edges = edge_index[-i] if layerwise_adjacency else edge_index
            x = torch.relu(layer(x, edges))
            x = F.dropout(x, p=self.dropout, training=self.training)

        edges = edge_index[0] if layerwise_adjacency else edge_index
        logits = self.sage_layers[-1](x, edges)
        logits = F.dropout(logits, p=self.dropout, training=self.training)

        memory_alloc = torch.cuda.memory_allocated() / (1024 * 1024)

        return logits, memory_alloc

class GCN(nn.Module):
    def __init__(self,
                 in_features: int,
                 hidden_dims: list[int], dropout: float=0.):
        super(GCN, self).__init__()
        self.dropout = dropout
        dims = [in_features] + hidden_dims
        gcn_layers = []
        for i in range(len(hidden_dims) - 1):
            gcn_layers.append(GCNConv(in_channels=dims[i],
                                      out_channels=dims[i + 1]))

        gcn_layers.append(GCNConv(in_channels=dims[-2], out_channels=dims[-1]))
        self.gcn_layers = nn.ModuleList(gcn_layers)

    def forward(self,
                x: torch.Tensor,
                edge_index: Union[torch.Tensor, list[torch.Tensor]],
                ) -> torch.Tensor:
        layerwise_adjacency = type(edge_index) == list

        for i, layer in enumerate(self.gcn_layers[:-1], start=1):
            edges = edge_index[-i] if layerwise_adjacency else edge_index
            x = torch.relu(layer(x, edges))
            x = F.dropout(x, p=self.dropout, training=self.training)

        edges = edge_index[0] if layerwise_adjacency else edge_index
        logits = self.gcn_layers[-1](x, edges)
        logits = F.dropout(logits, p=self.dropout, training=self.training)

        # torch.cuda.synchronize()
        memory_alloc = torch.cuda.memory_allocated() / (1024 * 1024)

        return logits, memory_alloc


class GAT(nn.Module):
    def __init__(self,
                 in_features: int,
                 hidden_dims: list[int]):
        super(GAT, self).__init__()

        dims = [in_features] + hidden_dims
        gat_layers = []
        for i in range(len(hidden_dims) - 1):
            gat_layers.append(GATConv(in_channels=dims[i],
                                      out_channels=dims[i + 1]))

        gat_layers.append(GATConv(in_channels=dims[-2], out_channels=dims[-1]))
        self.gat_layers = nn.ModuleList(gat_layers)

    def forward(self,
                x: torch.Tensor,
                edge_index: Union[torch.Tensor, list[torch.Tensor]],
                ) -> torch.Tensor:
        layerwise_adjacency = type(edge_index) == list

        for i, layer in enumerate(self.gat_layers[:-1], start=1):
            edges = edge_index[-i] if layerwise_adjacency else edge_index
            x = torch.relu(layer(x, edges))

        edges = edge_index[0] if layerwise_adjacency else edge_index
        logits = self.gat_layers[-1](x, edges)

        return logits


class GCN2(nn.Module):
    def __init__(self, in_features: int,
                 hidden_dims: list[int],
                 alpha: float, theta: float,
                 shared_weights=True, dropout=0.0):
        super(GCN2, self).__init__()

        lins = []
        lins.append(Linear(in_features, hidden_dims[0]))
        lins.append(Linear(hidden_dims[0], hidden_dims[1]))
        self.lins = nn.ModuleList(lins)

        conv = []
        for layer in range(len(hidden_dims)):
            conv.append(
                GCN2Conv(hidden_dims[0], alpha, theta, layer + 1,
                         shared_weights, normalize=False))

        self.conv = nn.ModuleList(conv)
        self.dropout = dropout

    def forward(self,
                x: torch.Tensor,
                edge_index: Union[torch.Tensor, list[torch.Tensor]],
                ) -> torch.Tensor:
        layerwise_adjacency = type(edge_index) == list

        x = F.dropout(x, self.dropout, training=self.training)
        x = x_0 = self.lins[0](x).relu()

        for i, layer in enumerate(self.conv[:-1], start=1):
            edges = edge_index[-i] if layerwise_adjacency else edge_index
            x = F.dropout(x, self.dropout, training=self.training)
            x = torch.relu(layer(x, x_0, edges))

        edges = edge_index[0] if layerwise_adjacency else edge_index
        x = F.dropout(x, self.dropout, training=self.training)
        x = self.conv[-1](x, x_0, edges)

        logits = self.lins[1](x)

        return logits


class PNA(nn.Module):
    def __init__(self, in_features: int, hidden_dims: list[int],
                 aggregators: list[str], scalers: list[str], deg: torch.Tensor, dropout: float = 0.0,
                 drop_input: bool = True, batch_norm: bool = False,
                 residual: bool = False, device=None):
        super(PNA, self).__init__()

        dims = [in_features] + hidden_dims
        self.conv = nn.ModuleList()
        for i in range(len(hidden_dims)):
            conv = PNAConv(in_channels=dims[i], out_channels=dims[i+1],aggregators=aggregators,
                           scalers=scalers, deg=deg)
            self.conv.append(conv)

        self.lins = Linear(in_features, hidden_dims[-1])

    def forward(self, x: torch.Tensor, edge_index: Union[torch.Tensor, list[torch.Tensor]],
                *args) -> torch.Tensor:
        layerwise_adjacency = type(edge_index) == list
        if self.drop_input:
            x = F.dropout(x, p=self.dropout, training=self.training)

        for i, layer in enumerate(self.conv[:-1], start=1):
            edges = edge_index[-i] if layerwise_adjacency else edge_index
            x = self.lins(x) # not sure!
            x = torch.relu(layer(x, edges))
            x = F.dropout(x, p=self.dropout, training=self.training)

        x = self.convs[-1](x,edge_index[-1])
        return x

