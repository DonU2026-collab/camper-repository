# Texterkennung (OCR)

Diese Dateien werden erst geladen, wenn in einem Tank- oder AdBlue-Formular ein Belegfoto gewählt wird. Sie liegen im Repository, damit die App ohne Fremdserver auskommt und das Foto das Gerät nicht verlässt.

| Datei | Quelle | Version | Lizenz |
|---|---|---|---|
| `tesseract.min.js`, `worker.min.js` | npm `tesseract.js` | 5.1.1 | Apache-2.0 |
| `tesseract-core-lstm.wasm.js`, `tesseract-core-simd-lstm.wasm.js` | npm `tesseract.js-core` | 5.1.1 | Apache-2.0 |
| `deu.traineddata.gz` | npm `@tesseract.js-data/deu` (`4.0.0_best_int`) | 1.0.0 | Apache-2.0 |

Austausch: Dateien aus den npm-Paketen gleichen Namens kopieren und `tests/test_features.py` laufen lassen.
