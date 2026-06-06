# Deep Quantized Trainer (py_simulator_v2)

This trainer exports a deeper MLP in an integer-friendly format for the RTL cycle demo.

## What changed

- Supports deeper architectures (e.g. `784 -> 256 -> 128 -> 10`)
- Uses QAT-style fake quantization during training
- Exports per-layer quantization metadata for stable multi-layer inference

## Train and export

```bash
cd /Users/junochun/Documents/DNN_with_RTL/py_simulator_v2/training
python dnn_trainer.py --hidden-dims 256,128 --epochs 10 --batch-size 64 --lr 0.001
```

Output file:

- `trained_dnn_weights.npz`

## Export format (`trained_dnn_weights.npz`)

- `MODEL_VERSION`: int (currently 2)
- `NUM_LAYERS`: number of linear layers
- `LAYER_DIMS`: full dims including input and output
- `W0..W{L-1}`: int weights, shape `(out_dim, in_dim)`
- `B0..B{L-1}`: float biases
- `W_SCALES`: per-layer weight scales
- `ACT_SCALES`: activation scales (`ACT_SCALES[0]` is input scale)

## Run the demo

```bash
cd /Users/junochun/Documents/DNN_with_RTL/py_simulator_v2/demo
python pygame_MNIST.py
```

The demo auto-detects both:

- legacy format (`W1`, `W2`)
- deep format (`W0..`, `B0..`, scales)
