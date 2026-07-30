#!/bin/bash
set -e
echo "Executing python patching script 0003..."
python3 -m patching.0003.patch_refetch_corrupted_history
echo "Patching 0003 complete!"
