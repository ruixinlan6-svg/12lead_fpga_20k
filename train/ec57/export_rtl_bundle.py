"""Export INT8 weight bundle, INT32 biases, and requantization parameters for FPGA RTL."""

import os
import json
import hashlib
import numpy as np
from typing import Dict, Any
from train.ec57.integer_reference import IntegerTinyECGCNN_NV


def compute_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


def export_rtl_bundle(model: IntegerTinyECGCNN_NV, output_dir: str) -> Dict[str, Any]:
    """
    Exports all weights, biases, and requantization multipliers into a deployable bundle.
    
    Files generated in `output_dir`:
      - weights_int8.bin: Flat binary byte array of all layer weights
      - bias_int32.bin: Little-endian 32-bit integer array of all biases
      - requant.json: Multiplier and shift parameters per channel
      - model_layout.json: Byte offsets, channel counts, and layer dimensions
      - bundle_manifest.json: Inventory and SHA-256 hashes
    """
    os.makedirs(output_dir, exist_ok=True)

    # 1. Pack weights into flat INT8 byte stream
    w1_bytes = model.conv1_w.tobytes()     # 8 * 1 * 7 = 56 bytes
    w2_bytes = model.conv2_w.tobytes()     # 16 * 8 * 5 = 640 bytes
    w3_bytes = model.conv3_w.tobytes()     # 16 * 16 * 3 = 768 bytes
    fc_w_bytes = model.fc_w.tobytes()      # 2 * 20 = 40 bytes

    all_weights = w1_bytes + w2_bytes + w3_bytes + fc_w_bytes
    weights_path = os.path.join(output_dir, 'weights_int8.bin')
    with open(weights_path, 'wb') as f:
        f.write(all_weights)

    # Also export hex format for Verilog $readmemh
    weights_hex_path = os.path.join(output_dir, 'weights_int8.hex')
    with open(weights_hex_path, 'w') as f:
        for b in all_weights:
            f.write(f"{b:02X}\n")

    # 2. Pack biases into little-endian INT32 stream
    b1_bytes = model.conv1_bias.astype('<i4').tobytes()    # 8 * 4 = 32 bytes
    b2_bytes = model.conv2_bias.astype('<i4').tobytes()    # 16 * 4 = 64 bytes
    b3_bytes = model.conv3_bias.astype('<i4').tobytes()    # 16 * 4 = 64 bytes
    fc_b_bytes = model.fc_bias.astype('<i4').tobytes()     # 2 * 4 = 8 bytes

    all_biases = b1_bytes + b2_bytes + b3_bytes + fc_b_bytes
    biases_path = os.path.join(output_dir, 'bias_int32.bin')
    with open(biases_path, 'wb') as f:
        f.write(all_biases)

    # Also export params_int32.hex for Verilog parameter memory initialization
    params_list = []
    # Conv1
    for oc in range(8):
        params_list.append(int(model.conv1_bias[oc]) & 0xFFFFFFFF)
        params_list.append(int(model.conv1_mult[oc]) & 0xFFFFFFFF)
        params_list.append(int(model.conv1_shift[oc]) & 0xFFFFFFFF)
    # Conv2
    for oc in range(16):
        params_list.append(int(model.conv2_bias[oc]) & 0xFFFFFFFF)
        params_list.append(int(model.conv2_mult[oc]) & 0xFFFFFFFF)
        params_list.append(int(model.conv2_shift[oc]) & 0xFFFFFFFF)
    # Conv3
    for oc in range(16):
        params_list.append(int(model.conv3_bias[oc]) & 0xFFFFFFFF)
        params_list.append(int(model.conv3_mult[oc]) & 0xFFFFFFFF)
        params_list.append(int(model.conv3_shift[oc]) & 0xFFFFFFFF)
    # FC
    for oc in range(2):
        params_list.append(int(model.fc_bias[oc]) & 0xFFFFFFFF)

    params_hex_path = os.path.join(output_dir, 'params_int32.hex')
    with open(params_hex_path, 'w') as f:
        for val in params_list:
            f.write(f"{val:08X}\n")
    requant_dict = {
        'conv1': {
            'mult': model.conv1_mult.tolist(),
            'shift': model.conv1_shift.tolist()
        },
        'conv2': {
            'mult': model.conv2_mult.tolist(),
            'shift': model.conv2_shift.tolist()
        },
        'conv3': {
            'mult': model.conv3_mult.tolist(),
            'shift': model.conv3_shift.tolist()
        }
    }
    requant_path = os.path.join(output_dir, 'requant.json')
    with open(requant_path, 'w', encoding='utf-8') as f:
        json.dump(requant_dict, f, indent=2)

    # 4. Export model memory layout
    layout_dict = {
        'model_name': 'TinyECGCNN_NV',
        'total_parameters': 1546,
        'total_weight_bytes': len(all_weights),
        'total_bias_bytes': len(all_biases),
        'layers': {
            'conv1': {
                'weight_offset_bytes': 0,
                'weight_size_bytes': len(w1_bytes),
                'bias_offset_bytes': 0,
                'bias_size_bytes': len(b1_bytes),
                'in_channels': 1,
                'out_channels': 8,
                'kernel_size': 7
            },
            'conv2': {
                'weight_offset_bytes': len(w1_bytes),
                'weight_size_bytes': len(w2_bytes),
                'bias_offset_bytes': len(b1_bytes),
                'bias_size_bytes': len(b2_bytes),
                'in_channels': 8,
                'out_channels': 16,
                'kernel_size': 5
            },
            'conv3': {
                'weight_offset_bytes': len(w1_bytes) + len(w2_bytes),
                'weight_size_bytes': len(w3_bytes),
                'bias_offset_bytes': len(b1_bytes) + len(b2_bytes),
                'bias_size_bytes': len(b3_bytes),
                'in_channels': 16,
                'out_channels': 16,
                'kernel_size': 3
            },
            'classifier': {
                'weight_offset_bytes': len(w1_bytes) + len(w2_bytes) + len(w3_bytes),
                'weight_size_bytes': len(fc_w_bytes),
                'bias_offset_bytes': len(b1_bytes) + len(b2_bytes) + len(b3_bytes),
                'bias_size_bytes': len(fc_b_bytes),
                'in_features': 20,
                'out_features': 2
            }
        }
    }
    layout_path = os.path.join(output_dir, 'model_layout.json')
    with open(layout_path, 'w', encoding='utf-8') as f:
        json.dump(layout_dict, f, indent=2)

    # 5. Compute manifest and total bundle hash
    manifest_files = {}
    total_hasher = hashlib.sha256()
    for fname in sorted(os.listdir(output_dir)):
        fpath = os.path.join(output_dir, fname)
        if os.path.isfile(fpath) and fname != 'bundle_manifest.json':
            sha = compute_sha256(fpath)
            manifest_files[fname] = sha
            total_hasher.update(sha.encode('utf-8'))

    bundle_manifest = {
        'bundle_name': 'TinyECGCNN_NV_INT8_Bundle',
        'bundle_sha256': total_hasher.hexdigest().upper(),
        'files': manifest_files
    }
    manifest_path = os.path.join(output_dir, 'bundle_manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(bundle_manifest, f, indent=2)

    return bundle_manifest
