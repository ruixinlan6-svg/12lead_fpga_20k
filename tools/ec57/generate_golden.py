"""Generates bit-exact core golden vectors for FPGA RTL and HIL verification."""

import os
import numpy as np
from typing import Dict, Any, Optional
from train.ec57.integer_reference import IntegerTinyECGCNN_NV


def generate_core_golden(
    model: IntegerTinyECGCNN_NV,
    num_beats: int = 4096,
    output_path: str = 'runs/golden/core_golden_v1.npz',
    seed: int = 20260828
) -> Dict[str, np.ndarray]:
    """
    Generates a dataset of `num_beats` synthetic test beats covering:
      - Normal QRS sinus beats
      - Broad premature ventricular ectopic beats (VEB)
      - Negative/inverted QRS complexes
      - Extreme dynamic ranges & saturation conditions
      - Low amplitude & flatline corner cases
    
    Returns a dictionary of arrays and saves to `output_path`.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    rng = np.random.RandomState(seed)

    input_wave = np.zeros((num_beats, 160), dtype=np.int8)
    input_feat = np.zeros((num_beats, 4), dtype=np.int8)

    pool1 = np.zeros((num_beats, 8, 80), dtype=np.int8)
    pool2 = np.zeros((num_beats, 16, 40), dtype=np.int8)
    conv3_act = np.zeros((num_beats, 16, 40), dtype=np.int8)
    gap = np.zeros((num_beats, 16), dtype=np.int8)
    concat = np.zeros((num_beats, 20), dtype=np.int8)
    logits = np.zeros((num_beats, 2), dtype=np.int32)
    classes = np.zeros(num_beats, dtype=np.int8)

    t_axis = np.linspace(-64, 95, 160)

    for i in range(num_beats):
        pattern_type = i % 8

        if pattern_type == 0:
            # Narrow Normal QRS (positive peak)
            width = rng.uniform(4.0, 8.0)
            amp = rng.uniform(40, 120)
            wave = amp * np.exp(-0.5 * (t_axis / width) ** 2) - 0.2 * amp * np.exp(-0.5 * ((t_axis + 12) / 6.0) ** 2)
            feat = np.array([0, -10, 10, 20], dtype=np.int8)

        elif pattern_type == 1:
            # Broad VEB (wide monophasic or biphasic)
            width = rng.uniform(14.0, 24.0)
            amp = rng.uniform(60, 127)
            wave = amp * np.exp(-0.5 * (t_axis / width) ** 2) - 0.5 * amp * np.exp(-0.5 * ((t_axis - 20) / 12.0) ** 2)
            feat = np.array([-25, 30, 20, 15], dtype=np.int8)

        elif pattern_type == 2:
            # Inverted VEB (negative deep S/QS wave)
            width = rng.uniform(16.0, 26.0)
            amp = rng.uniform(60, 125)
            wave = -amp * np.exp(-0.5 * (t_axis / width) ** 2) + 0.3 * amp * np.exp(-0.5 * ((t_axis - 25) / 15.0) ** 2)
            feat = np.array([-30, 32, -15, 18], dtype=np.int8)

        elif pattern_type == 3:
            # Saturated extreme signals (clamping check)
            wave = rng.choice([-128, 127, 0, 64, -64], size=160).astype(np.float64)
            feat = rng.randint(-128, 127, size=4).astype(np.int8)

        elif pattern_type == 4:
            # Low amplitude / near flatline
            wave = rng.uniform(-5, 5, size=160)
            feat = np.array([0, 0, -32, -32], dtype=np.int8)

        elif pattern_type == 5:
            # Biphasic premature beat with noise
            width = rng.uniform(10.0, 18.0)
            wave = 80 * np.sin(2 * np.pi * t_axis / 50.0) * np.exp(-0.5 * (t_axis / width) ** 2)
            noise = rng.normal(0, 8, size=160)
            wave = wave + noise
            feat = np.array([-15, 18, 5, 10], dtype=np.int8)

        elif pattern_type == 6:
            # High-frequency notch / pacemaker artifact
            wave = 100 * np.exp(-0.5 * (t_axis / 6.0) ** 2)
            wave[60:68] += rng.choice([-60, 60], size=8)
            feat = np.array([5, -5, 15, 25], dtype=np.int8)

        else:
            # Random uniform pseudo-random noise vector
            wave = rng.uniform(-100, 100, size=160)
            feat = rng.randint(-64, 64, size=4).astype(np.int8)

        # Quantize to INT8
        wave_int8 = np.clip(np.round(wave), -128, 127).astype(np.int8)
        feat_int8 = np.asarray(feat, dtype=np.int8)

        # Forward pass through integer reference
        acts = model.forward_with_intermediates(wave_int8, feat_int8)

        input_wave[i] = wave_int8
        input_feat[i] = feat_int8
        pool1[i] = acts['pool1']
        pool2[i] = acts['pool2']
        conv3_act[i] = acts['conv3_act']
        gap[i] = acts['gap']
        concat[i] = acts['concat']
        logits[i] = acts['logits']
        # Class 1 (VEB) if logit_veb > logit_non_veb
        classes[i] = 1 if acts['logits'][1] > acts['logits'][0] else 0

    golden_dict = {
        'input_wave': input_wave,
        'input_feat': input_feat,
        'pool1': pool1,
        'pool2': pool2,
        'conv3_act': conv3_act,
        'gap': gap,
        'concat': concat,
        'logits': logits,
        'classes': classes
    }

    np.savez_compressed(output_path, **golden_dict)
    return golden_dict
