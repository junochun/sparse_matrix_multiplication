import os
import sys
import numpy as np
import argparse

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

# Ensure the src directory is in the path to use the existing data loader
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'DNN_from_git', 'src'))
try:
    import mnist_loader
except ImportError:
    print("[ERROR] Could not import mnist_loader. Check path.")
    sys.exit(1)


class FakeQuantizeSTE(torch.autograd.Function):
    """
    Straight-Through Estimator for Quantization.
    Forward: quantizes the tensor to target min/max.
    Backward: passes the gradient unchanged.
    """
    @staticmethod
    def forward(ctx, x, qmin, qmax):
        return torch.round(x).clamp(qmin, qmax)

    @staticmethod
    def backward(ctx, grad_output):
        return grad_output, None, None

def fake_quantize(x, qmin, qmax):
    return FakeQuantizeSTE.apply(x, qmin, qmax)


def _parse_hidden_dims(text: str):
    parts = [p.strip() for p in text.split(',') if p.strip()]
    if not parts:
        return [256, 128]
    return [int(p) for p in parts]


def fake_quant_weight(weight: torch.Tensor):
    max_abs = weight.detach().abs().max()
    scale = torch.clamp(max_abs / 127.0, min=1e-8)
    q = fake_quantize(weight / scale, -127, 127)
    return q * scale


def fake_quant_activation_unsigned(x: torch.Tensor):
    max_val = x.detach().max()
    scale = torch.clamp(max_val / 127.0, min=1e-8)
    q = fake_quantize(x / scale, 0, 127)
    return q * scale


class DeepQATMLP(nn.Module):
    def __init__(self, hidden_dims):
        super(DeepQATMLP, self).__init__()
        dims = [784] + hidden_dims + [10]
        self.layers = nn.ModuleList([
            nn.Linear(dims[i], dims[i + 1], bias=True)
            for i in range(len(dims) - 1)
        ])

    def forward(self, x):
        x = fake_quant_activation_unsigned(x)
        last_idx = len(self.layers) - 1
        for i, layer in enumerate(self.layers):
            w_q = fake_quant_weight(layer.weight)
            x = F.linear(x, w_q, layer.bias)
            if i != last_idx:
                x = F.relu(x)
                x = fake_quant_activation_unsigned(x)
        return x

    def forward_float_collect(self, x):
        activations = []
        last_idx = len(self.layers) - 1
        for i, layer in enumerate(self.layers):
            x = layer(x)
            if i != last_idx:
                x = F.relu(x)
                activations.append(x)
        return x, activations


def collect_hidden_activation_scales(model, loader, device, max_batches=150):
    model.eval()
    per_layer_vals = None
    with torch.no_grad():
        for batch_idx, (data, _) in enumerate(loader):
            if batch_idx >= max_batches:
                break
            data = data.to(device)
            _, hiddens = model.forward_float_collect(data)
            if per_layer_vals is None:
                per_layer_vals = [[] for _ in hiddens]
            for layer_idx, hidden in enumerate(hiddens):
                per_layer_vals[layer_idx].append(hidden.detach().cpu().numpy())

    if per_layer_vals is None:
        return []

    scales = []
    for vals in per_layer_vals:
        concatenated = np.concatenate([v.reshape(-1) for v in vals], axis=0)
        p999 = float(np.percentile(concatenated, 99.9))
        scale = max(p999 / 127.0, 1e-8)
        scales.append(scale)
    return scales


def export_quantized(model, hidden_scales, save_path):
    model.eval()
    weight_scales = []
    layer_dims = [784]
    export_dict = {
        "MODEL_VERSION": np.array([2], dtype=np.int32),
    }

    for idx, layer in enumerate(model.layers):
        w = layer.weight.detach().cpu().numpy().astype(np.float32)
        b = layer.bias.detach().cpu().numpy().astype(np.float32)
        max_abs = float(np.max(np.abs(w)))
        w_scale = max(max_abs / 127.0, 1e-8)
        w_int = np.round(w / w_scale).clip(-127, 127).astype(np.int32)
        export_dict[f"W{idx}"] = w_int
        export_dict[f"B{idx}"] = b
        weight_scales.append(w_scale)
        layer_dims.append(w_int.shape[0])

    act_scales = [1.0 / 127.0] + hidden_scales

    export_dict["W_SCALES"] = np.array(weight_scales, dtype=np.float32)
    export_dict["ACT_SCALES"] = np.array(act_scales, dtype=np.float32)
    export_dict["LAYER_DIMS"] = np.array(layer_dims, dtype=np.int32)
    export_dict["NUM_LAYERS"] = np.array([len(model.layers)], dtype=np.int32)
    np.savez(save_path, **export_dict)


def train_and_save(hidden_dims, epochs, batch_size, lr):
    print("=== Starting Deep QAT-Style Training for Py_Simulator ===")
    print(f"Architecture: 784 -> {' -> '.join(map(str, hidden_dims))} -> 10")
    
    # 1. Load Data
    print("Loading data via mnist_loader...")
    training_data, validation_data, test_data = mnist_loader.load_data_wrapper()
    
    train_x = torch.FloatTensor(np.array([val[0] for val in training_data]).reshape(-1, 784))
    train_y = torch.FloatTensor(np.array([val[1] for val in training_data]).reshape(-1, 10))
    train_y_indices = torch.argmax(train_y, dim=1)
    
    test_x = torch.FloatTensor(np.array([val[0] for val in test_data]).reshape(-1, 784))
    test_y = torch.LongTensor(np.array([val[1] for val in test_data]))

    train_dataset = TensorDataset(train_x, train_y_indices)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    calib_loader = DataLoader(train_dataset, batch_size=256, shuffle=False)
    
    # 2. Build Model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = DeepQATMLP(hidden_dims).to(device)
    train_x = train_x.to(device)
    train_y_indices = train_y_indices.to(device)
    test_x = test_x.to(device)
    test_y = test_y.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)
    
    # 3. Train
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for batch_idx, (data, target) in enumerate(train_loader):
            data = data.to(device)
            target = target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            
            if batch_idx % 1000 == 0:
                print(f"Epoch {epoch+1} / {epochs} | Batch {batch_idx} | Loss: {loss.item():.4f}")
        
        # Step the scheduler at the end of epoch
        scheduler.step()
                
        # Eval
        model.eval()
        with torch.no_grad():
            test_out = model(test_x)
            pred = torch.argmax(test_out, dim=1)
            correct = (pred == test_y).sum().item()
            acc = correct / len(test_y)
            print(f"--> Epoch {epoch+1} Test Accuracy: {acc:.2%}")

    # 4. Export Quantized Parameters for Simulator
    print("\nCollecting calibration scales and exporting quantized model...")
    hidden_scales = collect_hidden_activation_scales(model, calib_loader, device)

    save_path = os.path.join(os.path.dirname(__file__), "trained_dnn_weights.npz")
    export_quantized(model, hidden_scales, save_path)
    print(f"Weights successfully saved to: {save_path}")
    print(f"Activation scales count: {len(hidden_scales) + 1}")
    print("Saved keys: MODEL_VERSION, NUM_LAYERS, LAYER_DIMS, W{i}, B{i}, W_SCALES, ACT_SCALES")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deep QAT-style MNIST trainer for py_simulator_v2")
    parser.add_argument("--hidden-dims", type=str, default="256,128", help="Comma-separated hidden dims, e.g. 256,128,64")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate")
    args = parser.parse_args()

    hidden_dims = _parse_hidden_dims(args.hidden_dims)
    train_and_save(hidden_dims, args.epochs, args.batch_size, args.lr)
