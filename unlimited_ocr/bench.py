import sys, time, glob, os
import mlx.core as mx

from mlx_vlm import load, generate

model_id, pages_dir, out_dir, prompt = sys.argv[1:5]
os.makedirs(out_dir, exist_ok=True)
t = time.time()
model, processor = load(model_id)
print(f"load: {time.time()-t:.1f}s", flush=True)

for img in sorted(glob.glob(f"{pages_dir}/*.png")):
    if len(sys.argv) > 5 and os.path.basename(img)[:-4] not in sys.argv[5].split(","): continue
    if os.path.exists(f"{out_dir}/{os.path.basename(img)[:-4]}.md"): continue  # resume
    t = time.time()
    r = generate(model, processor, prompt=prompt, image=img, max_tokens=4096, temperature=0.0, verbose=False)
    dt = time.time() - t
    name = os.path.basename(img)[:-4]
    open(f"{out_dir}/{name}.md", "w").write(r.text)
    print(f"{name}: {dt:.1f}s  gen_tok={r.generation_tokens} {r.generation_tps:.0f} tok/s  "
          f"prompt_tok={r.prompt_tokens}  peak={mx.get_peak_memory()/1e9:.2f} GB", flush=True)
