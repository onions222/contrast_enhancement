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
    
    # 阈值：忽略像素占比小于 0.05% 的桶，避免噪点干扰
    noise_th = total_pixels * 0.0005
    active_mask = hist > noise_th
    active_indices = np.where(active_mask)[0]
    
    if len(active_indices) == 0:
        return None 
    
    first_active = active_indices[0]
    last_active = active_indices[-1]
    
    active_bin_count = len(active_indices)
    span = last_active - first_active + 1
    
    runs = []
    if active_bin_count > 0:
        current_run = 1
        for i in range(1, len(active_indices)):
            if active_indices[i] == active_indices[i-1] + 1:
                current_run += 1
            else:
                runs.append(current_run)
                current_run = 1
        runs.append(current_run)
    
    active_run_count = len(runs)
    longest_run = max(runs) if runs else 0
    hole_count = span - active_bin_count
    
    max_bin_val = np.max(hist)
    max_bin_ratio = max_bin_val / total_pixels
    # SAD 归一化到像素总数
    sum_abs_diff = np.sum(np.abs(np.diff(hist.astype(np.float32)))) / total_pixels
    
    active_bins = hist[active_mask]
    flatness = np.min(active_bins) / np.max(active_bins) if len(active_bins) > 0 else 0
    
    return {
        "name": os.path.basename(img_path),
        "active_bins": active_bin_count,
        "span": span,
        "runs": active_run_count,
        "max_run": longest_run,
        "holes": hole_count,
        "max_ratio": round(max_bin_ratio, 3),
        "sad": round(sum_abs_diff, 3),
        "flat": round(flatness, 3)
    }

pattern_dir = "data/raw/starter_synth_v1/*.png"
files = glob.glob(pattern_dir)
results = []
for f in sorted(files):
    stats = analyze_image_stats(f)
    if stats:
        results.append(stats)

header = f"{'Filename':<40} | Act | Span | Run | MaxR | Hole | MaxRatio | SAD   | Flat"
print(header)
print("-" * len(header))
for r in results:
    print(f"{r['name']:<40} | {r['active_bins']:<3} | {r['span']:<4} | {r['runs']:<3} | {r['max_run']:<4} | {r['holes']:<4} | {r['max_ratio']:<8} | {r['sad']:<5} | {r['flat']}")
