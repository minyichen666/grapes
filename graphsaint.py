import argparse
import os

import torch
import torch.nn as nn

from torch_geometric.loader import GraphSAINTNodeSampler
from modules.gcn import GCN
from modules.data import get_data

parser = argparse.ArgumentParser()
parser.add_argument('--use_normalization', action='store_true')
parser.add_argument('--hidden_dim', default=256, type=int)
parser.add_argument('--dataset', type=str)
parser.add_argument('--runs', default=1, type=int)
args = parser.parse_args()


def train(model, loader, loss_fn):
    model.train()
    total_loss = total_examples = 0
    for batch in loader:
        batch = batch.to(device)
        optimizer.zero_grad()

        out = model(batch.x, batch.edge_index)
        train_idx = batch.train_mask.nonzero().squeeze(1)
        loss = loss_fn(out[train_idx],
                                   batch.y[train_idx])

        loss.backward()
        optimizer.step()
        total_loss += loss.item() * data.num_nodes
        total_examples += data.num_nodes
    return total_loss / total_examples


@torch.no_grad()
def test(model, data):
    model.eval()
    out = model(data.x.to('cpu'), data.edge_index.to('cpu'))
    if data.y.dim() == 1:
        pred = out.argmax(dim=-1)
        correct = pred.eq(data.y.to('cpu'))

        # accs = []
        # train_acc = correct[data.train_mask].float().mean().item()
        # val_acc = correct[data.val_mask].float().mean().item()
        test_acc = correct[data.test_mask].float().mean().item()

    # multilabel classification
    else:
        y_pred = out > 0
        y_true = data.y > 0.5

        tp = int((y_true[data.test_mask].to('cpu') & y_pred[data.test_mask].to('cpu')).sum())
        fp = int((~y_true[data.test_mask].to('cpu') & y_pred[data.test_mask].to('cpu')).sum())
        fn = int((y_true[data.test_mask].to('cpu') & ~y_pred[data.test_mask].to('cpu')).sum())

        try:
            precision = tp / (tp + fp)
            recall = tp / (tp + fn)
            test_acc = accuracy = 2 * (precision * recall) / (precision + recall)
        except ZeroDivisionError:
            test_acc = 0.

    return test_acc


results = torch.empty(args.runs)
for run in range(args.runs):
    path = os.path.join(os.getcwd(), 'data', args.dataset)
    data, num_features, num_classes = get_data(root=path, name=args.dataset)
    row, col = data.edge_index

    loader = GraphSAINTNodeSampler(data, batch_size=768)

    if data.y.dim() == 1:
        loss_fn = nn.CrossEntropyLoss()
    else:
        loss_fn = nn.BCEWithLogitsLoss()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = GCN(data.num_features, hidden_dims=[args.hidden_dim, num_classes]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    for epoch in range(1, 101):
        loss = train(model, loader, loss_fn)
        accs = test(model, data)
        print(f'Epoch: {epoch:02d}, Loss: {loss:.4f}, Test: {accs:.4f}')

    results[run] = accs
print(f'Mini Acc: {100 * results.mean():.2f} ± {100 * results.std():.2f}')