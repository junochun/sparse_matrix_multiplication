import os
import sys
import numpy as np
import scipy.ndimage

_DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DEMO_DIR)
sys.path.insert(0, _ROOT)

from core import sparse_RTL_simulator as sim

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['SDL_DISABLE_MACOS_IMK'] = '1'
try:
    import pygame
except ImportError:
    print("[ERROR] Pygame not found. Please install via: conda install pygame or pip install pygame")
    sys.exit(1)

# Pygame Setup
WIDTH, HEIGHT = 640, 420
UI_HEIGHT = 260
WIN = pygame.display.set_mode((WIDTH, HEIGHT + UI_HEIGHT))
pygame.display.set_caption("RTL Simulator Interactive Demo")

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY  = (100, 100, 100)
GREEN = (0, 255, 0)

# Pre-load Weight Arrays
weight_path = os.path.join(_ROOT, 'training', 'trained_dnn_weights.npz')
if not os.path.exists(weight_path):
    print(f"[ERROR] Trained weights not found at {weight_path}")
    print("Please run 'python dnn_trainer.py' to train and save weights.")
    sys.exit(1)

def load_quantized_model(npz_path):
    data = np.load(npz_path)
    keys = set(data.files)

    # New deep format: W0..Wn, B0..Bn, W_SCALES, ACT_SCALES
    if "NUM_LAYERS" in keys and "W_SCALES" in keys and "ACT_SCALES" in keys and "W0" in keys:
        num_layers = int(np.array(data["NUM_LAYERS"]).reshape(-1)[0])
        w_scales = np.array(data["W_SCALES"], dtype=np.float32).reshape(-1)
        act_scales = np.array(data["ACT_SCALES"], dtype=np.float32).reshape(-1)

        layers = []
        for layer_idx in range(num_layers):
            w_key = f"W{layer_idx}"
            b_key = f"B{layer_idx}"
            if w_key not in keys:
                raise KeyError(f"Missing key '{w_key}' in {npz_path}")

            w_out_in = np.array(data[w_key], dtype=np.int32)  # (out, in)
            b = np.array(data[b_key], dtype=np.float32).reshape(-1) if b_key in keys else np.zeros((w_out_in.shape[0],), dtype=np.float32)

            layers.append({
                "w_t": w_out_in.T.copy(),
                "bias": b,
                "in_dim": int(w_out_in.shape[1]),
                "out_dim": int(w_out_in.shape[0]),
            })

        return {
            "layers": layers,
            "w_scales": w_scales,
            "act_scales": act_scales,
            "format": "deep_qat_v2",
        }

    # Legacy 2-layer format
    if "W1" not in keys or "W2" not in keys:
        raise KeyError("Unsupported weight file format. Need (W1,W2) or deep format (W0.., B0.., W_SCALES, ACT_SCALES).")

    w1_out_in = np.array(data["W1"], dtype=np.int32)
    w2_out_in = np.array(data["W2"], dtype=np.int32)

    layers = [
        {"w_t": w1_out_in.T.copy(), "bias": np.zeros((w1_out_in.shape[0],), dtype=np.float32), "in_dim": int(w1_out_in.shape[1]), "out_dim": int(w1_out_in.shape[0])},
        {"w_t": w2_out_in.T.copy(), "bias": np.zeros((w2_out_in.shape[0],), dtype=np.float32), "in_dim": int(w2_out_in.shape[1]), "out_dim": int(w2_out_in.shape[0])},
    ]
    return {
        "layers": layers,
        "w_scales": np.array([1.0 / 127.0, 1.0 / 127.0], dtype=np.float32),
        "act_scales": np.array([1.0 / 127.0, 1.0 / 127.0], dtype=np.float32),
        "format": "legacy_v1",
    }


MODEL = load_quantized_model(weight_path)
NUM_LAYERS = len(MODEL["layers"])
FIRST_HIDDEN_DIM = MODEL["layers"][0]["out_dim"] if NUM_LAYERS > 1 else MODEL["layers"][-1]["out_dim"]
MODEL_FORMAT = MODEL.get("format", "unknown")
MODEL_DIMS = [MODEL["layers"][0]["in_dim"]] + [layer["out_dim"] for layer in MODEL["layers"]]
MODEL_ARCH = "-".join(str(dim) for dim in MODEL_DIMS)

pygame.font.init()
FONT = pygame.font.SysFont('Arial', 20)
SMALL_FONT = pygame.font.SysFont('Arial', 18)
TINY_FONT = pygame.font.SysFont('Arial', 16)

def draw_grid_and_ui(
    win,
    sparse_cycles_total=0,
    dense_cycles_total=0,
    prediction=-1,
    input_nnz=0,
    hidden_nnz=0,
    hidden_dim=100,
    per_layer_sparse_cycles=None,
    per_layer_dense_cycles=None,
    per_layer_skip_ratios=None,
):
    if per_layer_sparse_cycles is None:
        per_layer_sparse_cycles = []
    if per_layer_dense_cycles is None:
        per_layer_dense_cycles = []
    if per_layer_skip_ratios is None:
        per_layer_skip_ratios = []

    win.fill(BLACK, (0, HEIGHT, WIDTH, UI_HEIGHT))
    pygame.draw.line(win, WHITE, (0, HEIGHT), (WIDTH, HEIGHT), 2)
    
    # Texts
    inst_text = SMALL_FONT.render("Draw a number!  (C: clear, Space: predict)", True, GRAY)
    win.blit(inst_text, (10, HEIGHT + 10))
    model_text = TINY_FONT.render(f"Arch: {MODEL_ARCH} | Layers: {NUM_LAYERS} | Format: {MODEL_FORMAT}", True, GRAY)
    win.blit(model_text, (10, HEIGHT + 32))
    
    if prediction != -1:
        pred_text = FONT.render(f"Predicted Digit: {prediction}", True, GREEN)
        win.blit(pred_text, (10, HEIGHT + 56))

        cycle_text_sparse = FONT.render(f"Sparse RTL Cycles: {sparse_cycles_total:,}", True, WHITE)
        win.blit(cycle_text_sparse, (10, HEIGHT + 88))

        cycle_text_dense = FONT.render(f"Dense RTL Cycles:  {dense_cycles_total:,}", True, GRAY)
        win.blit(cycle_text_dense, (10, HEIGHT + 118))

        speedup = dense_cycles_total / sparse_cycles_total if sparse_cycles_total > 0 else 0.0
        speedup_text = FONT.render(f"Dense/Sparse Ratio: {speedup:.2f}x", True, GRAY)
        win.blit(speedup_text, (10, HEIGHT + 148))

        input_text = SMALL_FONT.render(
            f"Input NNZ:  {input_nnz}/784 ({(input_nnz / 784.0) * 100.0:.1f}%)", True, GRAY
        )
        win.blit(input_text, (340, HEIGHT + 56))

        hidden_text = SMALL_FONT.render(
            f"Hidden NNZ: {hidden_nnz}/{hidden_dim} ({(hidden_nnz / max(hidden_dim, 1)) * 100.0:.1f}%)", True, GRAY
        )
        win.blit(hidden_text, (340, HEIGHT + 80))

        detail_header = TINY_FONT.render("Per-layer (Sparse / Dense / Skip):", True, WHITE)
        win.blit(detail_header, (340, HEIGHT + 112))
        max_detail_lines = 4
        for layer_idx in range(min(len(per_layer_sparse_cycles), len(per_layer_dense_cycles), len(per_layer_skip_ratios), max_detail_lines)):
            detail_line = TINY_FONT.render(
                f"L{layer_idx + 1}: {per_layer_sparse_cycles[layer_idx]:,} / {per_layer_dense_cycles[layer_idx]:,} / {per_layer_skip_ratios[layer_idx] * 100.0:.1f}%",
                True,
                GRAY,
            )
            win.blit(detail_line, (340, HEIGHT + 134 + (layer_idx * 20)))


def extract_and_resize(surface):
    # Extract WIDTH x HEIGHT surface as numpy array
    drawn_img = pygame.surfarray.array3d(surface)[:WIDTH, :HEIGHT, 0] # Use one channel (Red) 
    drawn_img = np.transpose(drawn_img) # Pygame has x,y but numpy uses r,c

    # Find bounding box to crop the digit tightly
    non_zero_pts = np.argwhere(drawn_img > 0)
    if len(non_zero_pts) == 0:
        return np.zeros((1, 784), dtype=np.int32)
        
    y_min, y_max = non_zero_pts[:, 0].min(), non_zero_pts[:, 0].max()
    x_min, x_max = non_zero_pts[:, 1].min(), non_zero_pts[:, 1].max()
    
    # Crop the digit
    cropped = drawn_img[y_min:y_max+1, x_min:x_max+1]
    
    # Calculate aspect ratio preserving scale to fit into 20x20 box (MNIST standard)
    h, w = cropped.shape
    max_dim = max(h, w)
    scale = 20.0 / max_dim
    # Apply scipy.ndimage.zoom to scale it down
    scaled = scipy.ndimage.zoom(cropped, scale, order=1)
    
    # Place scaled image into 28x28 box
    small_img = np.zeros((28, 28), dtype=np.float32)
    sh, sw = scaled.shape
    y_off = (28 - sh) // 2
    x_off = (28 - sw) // 2
    small_img[y_off:y_off+sh, x_off:x_off+sw] = scaled

    # Scipy center of mass to shift digit to middle (similar to MNIST dataset preprocessing)
    cy, cx = scipy.ndimage.center_of_mass(small_img)
    if not np.isnan(cy) and not np.isnan(cx):
        shift_y = 14 - int(cy)
        shift_x = 14 - int(cx)
        small_img = scipy.ndimage.shift(small_img, (shift_y, shift_x))

    # Normalize to 0~127 since QAT quantization used 0~127
    max_val = np.max(small_img)
    if max_val > 0:
        small_img = (small_img / max_val) * 127.0
        
    flattened = np.round(small_img).astype(np.int32).reshape(1, 784)
    return flattened


def run_inference_via_rtl(img_vector):
    print("\n" + "="*40)
    print("      Starting RTL Forward Inference    ")
    print("="*40)
    
    layers = MODEL["layers"]
    w_scales = MODEL["w_scales"]
    act_scales = MODEL["act_scales"]

    sparse_cycles_total = 0
    dense_cycles_total = 0
    layer_skip_ratios = []
    layer_sparse_cycles = []
    layer_dense_cycles = []

    input_nnz = int(np.count_nonzero(img_vector))
    hidden_nnz = 0

    act_int = img_vector.astype(np.int32)
    logits = None

    for layer_idx, layer in enumerate(layers):
        w_t = layer["w_t"]
        bias = layer["bias"]

        k_size = w_t.shape[0]
        n_size = w_t.shape[1]
        print(f"\n[Layer {layer_idx + 1}] fc{layer_idx + 1}")
        print(f"  - Matrix A : 1 x {act_int.shape[1]}")
        print(f"  - Matrix B : {k_size} x {n_size}")

        sparse_res = sim.run_simulation(
            m_size=1,
            k_size=k_size,
            n_size=n_size,
            sa_size=64,
            verbose=False,
            val_a=act_int,
            val_b=w_t,
        )
        dense_res = sim.run_simulation(
            m_size=1,
            k_size=k_size,
            n_size=n_size,
            sa_size=64,
            verbose=False,
            val_a=act_int,
            val_b=w_t,
            dense_mode=True,
        )

        sparse_cyc = int(sparse_res["total_cycles"])
        dense_cyc = int(dense_res["total_cycles"])
        layer_skip = float(sparse_res.get("skip_ratio", 0.0))
        sparse_cycles_total += sparse_cyc
        dense_cycles_total += dense_cyc
        layer_skip_ratios.append(layer_skip)
        layer_sparse_cycles.append(sparse_cyc)
        layer_dense_cycles.append(dense_cyc)

        print(f"  --> [fc{layer_idx + 1}] Sparse Cycles: {sparse_cyc:,}")
        print(f"  --> [fc{layer_idx + 1}] Dense  Cycles: {dense_cyc:,}")

        act_scale_in = float(act_scales[layer_idx]) if layer_idx < len(act_scales) else (1.0 / 127.0)
        w_scale = float(w_scales[layer_idx]) if layer_idx < len(w_scales) else (1.0 / 127.0)

        z_int = act_int.astype(np.int64) @ w_t.astype(np.int64)
        z_real = z_int.astype(np.float32) * (act_scale_in * w_scale) + bias.reshape(1, -1)

        is_last = (layer_idx == len(layers) - 1)
        if is_last:
            logits = z_real
        else:
            relu_real = np.maximum(z_real, 0.0)
            act_scale_out = float(act_scales[layer_idx + 1]) if (layer_idx + 1) < len(act_scales) else max(float(np.max(relu_real)) / 127.0, 1e-8)
            act_scale_out = max(act_scale_out, 1e-8)
            act_int = np.clip(np.round(relu_real / act_scale_out), 0, 127).astype(np.int32)
            if layer_idx == 0:
                hidden_nnz = int(np.count_nonzero(act_int))

    if hidden_nnz == 0 and len(layers) > 1:
        hidden_nnz = int(np.count_nonzero(act_int))

    predicted_digit = int(np.argmax(logits)) if logits is not None else 0
    layer1_skip_ratio = layer_skip_ratios[0] if layer_skip_ratios else 0.0
    last_layer_skip_ratio = layer_skip_ratios[-1] if layer_skip_ratios else 0.0
    print("\n" + "-"*40)
    print(f"  Prediction: {predicted_digit}")
    print(f"  Total Sparse RTL Cycles: {sparse_cycles_total:,}")
    print(f"  Total Dense  RTL Cycles: {dense_cycles_total:,}")
    if sparse_cycles_total > 0:
        print(f"  Dense/Sparse Ratio: {dense_cycles_total / sparse_cycles_total:.2f}x")
    print(f"  Input NNZ (1x784): {input_nnz}/784 ({(input_nnz / 784.0) * 100.0:.1f}%)")
    print(f"  Hidden NNZ (1x{FIRST_HIDDEN_DIM}): {hidden_nnz}/{FIRST_HIDDEN_DIM} ({(hidden_nnz / max(FIRST_HIDDEN_DIM, 1)) * 100.0:.1f}%)")
    print(f"  L1 Sparse Skip Ratio: {layer1_skip_ratio * 100.0:.1f}%")
    print(f"  Last Layer Sparse Skip Ratio: {last_layer_skip_ratio * 100.0:.1f}%")
    print("-"*40)

    return (
        predicted_digit,
        sparse_cycles_total,
        dense_cycles_total,
        input_nnz,
        hidden_nnz,
        layer_sparse_cycles,
        layer_dense_cycles,
        layer_skip_ratios,
    )


def main():
    run = True
    drawing = False
    
    canvas = pygame.Surface((WIDTH, HEIGHT))
    canvas.fill(BLACK)
    
    prediction = -1
    sparse_cycles = 0
    dense_cycles = 0
    input_nnz = 0
    hidden_nnz = 0
    layer_sparse_cycles = []
    layer_dense_cycles = []
    layer_skip_ratios = []

    while run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
                
            # Drawing Logic
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                if my < HEIGHT:
                    drawing = True
                    last_pos = (mx, my)
                    pygame.draw.circle(canvas, WHITE, (mx, my), 12)
            elif event.type == pygame.MOUSEBUTTONUP:
                drawing = False
            elif event.type == pygame.MOUSEMOTION and drawing:
                mx, my = pygame.mouse.get_pos()
                if my < HEIGHT:
                    # Draw line from last_pos to current to prevent dots
                    pygame.draw.line(canvas, WHITE, last_pos, (mx, my), 24)
                    # Also draw circle to make edges smooth
                    pygame.draw.circle(canvas, WHITE, (mx, my), 12)
                    last_pos = (mx, my)

            # Keybindings
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_c:
                    canvas.fill(BLACK)
                    prediction = -1
                    sparse_cycles = 0
                    dense_cycles = 0
                    input_nnz = 0
                    hidden_nnz = 0
                    layer_sparse_cycles = []
                    layer_dense_cycles = []
                    layer_skip_ratios = []
                elif event.key == pygame.K_SPACE:
                    img_vec = extract_and_resize(canvas)
                    if np.max(img_vec) > 0: # Ensure not empty
                        (
                            prediction,
                            sparse_cycles,
                            dense_cycles,
                            input_nnz,
                            hidden_nnz,
                            layer_sparse_cycles,
                            layer_dense_cycles,
                            layer_skip_ratios,
                        ) = run_inference_via_rtl(img_vec)

        # Draw
        WIN.blit(canvas, (0, 0))
        draw_grid_and_ui(
            WIN,
            sparse_cycles,
            dense_cycles,
            prediction,
            input_nnz,
            hidden_nnz,
            FIRST_HIDDEN_DIM,
            layer_sparse_cycles,
            layer_dense_cycles,
            layer_skip_ratios,
        )
        pygame.display.update()

    pygame.quit()


if __name__ == "__main__":
    main()
