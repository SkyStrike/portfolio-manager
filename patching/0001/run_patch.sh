#!/bin/bash
set -e
echo "Executing python patching script..."
python3 -m patching.0001.patch_dividends_qty
echo "Patching complete!"
