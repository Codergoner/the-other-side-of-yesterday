"""Compare the rendered reference camera against the supplied image."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parent
source = np.asarray(Image.open(root / 'assets' / 'harbor_reference.png').convert('RGB'), dtype=np.int16)
render = np.asarray(Image.open(root / 'output' / 'Harbor_reference_match.png').convert('RGB'), dtype=np.int16)
error = np.abs(source - render)
report = {
    'resolution': [int(source.shape[1]), int(source.shape[0])],
    'mean_absolute_channel_error_out_of_255': round(float(error.mean()), 6),
    'maximum_channel_error_out_of_255': int(error.max()),
    'channels_within_one_level_percent': round(float((error <= 1).mean() * 100), 5),
    'method': 'Camera-projected 2.5D geometry with independent editable modeled assets',
    'limitation': 'Source-camera appearance is preserved; hidden surfaces and views from other angles are approximations.',
}
(root / 'output' / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
