# CadenceAI experiments

How well does each approach capture how a song *sounds*? Each script embeds the same 89 Deezer
previews (10 genres, 3 artists per genre, 3 songs per artist) and checks whether a song's 5
closest-sounding songs **by other artists** share its genre (precision@5). Genre is a rough stand-in
for "sounds alike", but it's measurable.

| Method | Precision@5 | Nearest neighbor | Time per song (CPU) | Model |
|---|---|---|---|---|
| Random guessing | 0.07 | — | — | — |
| Original summer formula | 0.11 | 0.18 | ~240 ms | — |
| Current librosa formula | 0.22 | 0.28 | ~240 ms | — |
| librosa without tempo/key | 0.28 | 0.36 | ~240 ms | — |
| MERT-95M (best layer, centered) | 0.49 | 0.63 | ~750 ms | 95M params |
| MERT-330M (best layer, centered) | 0.57 | 0.62 | ~1,500 ms | 315M params |
| CLAP `larger_clap_general` | 0.65 | 0.66 | ~200 ms | 194M params |
| **Discogs-EffNet** | **0.69–0.71** | **0.73** | ~410 ms | 18 MB |

CLAP also understands text: labeling genre from prompts like "jazz music" was 81% correct, and
searches like "calm solo piano" or "drum machine and synthesizers" returned sensible songs.
`laion/larger_clap_music` is broken on Hugging Face (every prompt gets nearly the same embedding),
so the general checkpoint is used.

With 89 songs, differences of a few points are noise; the gap between librosa and the models is not.

## Running

```bash
python experiments/genre_eval.py    # downloads previews, librosa results (app requirements)
python experiments/effnet_eval.py   # pip install essentia-tensorflow
python experiments/clap_eval.py     # pip install torch transformers librosa
python experiments/mert_eval.py     # also pip install nnAudio; runs model code from the m-a-p repo
```

Previews, models and embeddings are cached in `experiments/.cache` (not committed).
