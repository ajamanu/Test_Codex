# Inventory Merge Assistant

This app lets you upload an Excel file with inventory data, detect similar descriptions, and merge inventory IDs for those similar SKUs.

## Expected Excel Columns

- `inventory_id`: unique inventory identifier.
- `description`: item description used for similarity matching.

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in your browser and upload your Excel file.

## Output

After reviewing the suggested merges, the app downloads an Excel file with an added `merged_inventory_id` column.
