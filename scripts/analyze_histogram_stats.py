import os
import numpy as np
from PIL import Image
import glob

def analyze_image_stats(img_path, num_bins=32):
    try:
        img = Image.open(img_path).convert('L')
    except Exception:
        return None
    data = np.array(img).flatten()
    total_pixels = data.size
    
    # 计算 32 阶直方图
    hist, _ = np.histogram(data, bins=num_bins, range=(0, 256))
    threshold = total_pixels >> 10
    active_mask = hist > threshold
    active_indices = np.where(active_mask)[0]

    if len(active_indices) == 0:
        return None

    first_active = int(active_indices[0])
    last_active = int(active_indices[-1])
    active_count = int(len(active_indices))
    span = int(last_active - first_active + 1)

    connectivity_count = 0
    for i in range(num_bins - 1):
        if active_mask[i] and active_mask[i + 1]:
            connectivity_count += 1
    run_count = active_count - connectivity_count

    max_bin_val = int(np.max(hist))
    max_bin_ratio = max_bin_val / total_pixels

    bypass_reason = ""
    if active_count <= 2:
        bypass_reason = "uniform_sparse"
    elif run_count * 4 > active_count:
        bypass_reason = "disconnected_comb"
    elif run_count == 1 and active_count >= 24 and span >= 24 and max_bin_val * 16 <= total_pixels:
        bypass_reason = "continuous_artificial"
    
    return {
        "name": os.path.basename(img_path),
        "active_count": active_count,
        "connectivity_count": connectivity_count,
        "run_count": run_count,
        "span": span,
        "first_active": first_active,
        "last_active": last_active,
        "threshold": threshold,
        "max_bin": max_bin_val,
        "max_ratio": round(max_bin_ratio, 3),
        "bypass_reason": bypass_reason if bypass_reason else "none",
    }

pattern_dir = "data/raw/starter_synth_v1/*.png"
files = glob.glob(pattern_dir)
results = []
for f in sorted(files):
    stats = analyze_image_stats(f)
    if stats:
        results.append(stats)

header = f"{'Filename':<40} | A   | C   | R   | F    | Thr | Pmax | PmaxRatio | Reason"
print(header)
print("-" * len(header))
for r in results:
    print(
        f"{r['name']:<40} | {r['active_count']:<3} | {r['connectivity_count']:<3} | "
        f"{r['run_count']:<3} | {r['span']:<4} | {r['threshold']:<3} | {r['max_bin']:<4} | "
        f"{r['max_ratio']:<9} | {r['bypass_reason']}"
    )
