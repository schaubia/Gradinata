# 🌿 Gradinata

**Smart Garden Assistant**
Plan new plants, manage care for existing ones, and track climate projections — all in one place.

Built by **Dantara Software EOOD**

---

## What the app does

Gradinata consolidates two standalone projects into one product:

- **Planning** — enter your garden's GPS coordinates and receive personalised plant recommendations based on real climate data, soil conditions, and climate projections
- **Care** — load your plant list and get a concrete schedule: when to prune, feed, and water, with automatic weather alerts for frost, drought, and high UV

The key connection between the two: once you generate a plan, the plants are automatically loaded into the care schedule — no manual entry required.

---

## File structure

```
gradinata_app.py          ← main file (run this)
garden_planner_core.py    ← recommendation and clustering logic
climate_projection.py     ← IPCC-based climate projections
gradinata_template.csv    ← template for manually entering plants
README.md                 ← this file
```

> **Important:** `garden_planner_core.py` and `climate_projection.py` must be in the same folder as `gradinata_app.py`. Without them the 🗺️ Planning, 📐 Garden Grid, and 🌍 Climate tabs will not work, but all other tabs (Dashboard, Care Schedule, Sun Setup, Template) are fully functional on their own.

---

## Installation

### Requirements

- Python 3.9 or newer
- pip

### Steps

```bash
# 1. Clone or extract the project
cd gradinata

# 2. Install dependencies
pip install streamlit pandas pillow openpyxl

# 3. Run
streamlit run gradinata_app.py
```

The app opens automatically at `http://localhost:8501`

### Deploying to the cloud (Streamlit Community Cloud)

1. Push all files to a GitHub repository
2. Log in at [share.streamlit.io](https://share.streamlit.io)
3. Connect the repo → select `gradinata_app.py` → Deploy

---

## Tabs and features

### 🗺️ Planning
Enter coordinates (latitude/longitude) and preferences, click **Generate**, and receive:
- A ranked list of recommended plants based on real suitability scores
- Companion planting clusters (which plants grow well together)
- Automatic loading of all plants into the Care Schedule tab

### 🌤️ Dashboard
- Live weather for your location (Open-Meteo API)
- 7-day forecast
- Tasks due this month
- Alerts for frost, dry soil, high UV, and heavy rain

### 📋 Care Schedule
Three views:
- **By month** — all tasks for a selected month
- **By plant** — full care card with pruning, feeding, and watering instructions
- **Mismatches only** — plants placed in the wrong light conditions

### ☀️ Sun Setup
Assign the actual sun exposure for each plant (full sun / partial shade / full shade). The app compares this against the plant's requirements and flags any mismatches.

### 📐 Garden Grid
A visual drag-and-drop garden grid, colour-coded by companion planting clusters. Download as a standalone HTML file that works offline.

### 🌍 Climate
Climate projection for your area based on IPCC data — expected changes in temperature, rainfall, and growing season length.

### ⬇️ Template
A CSV template for manually entering your plant list. Download, fill in, upload via the sidebar.

---

## Loading your plants

**Option A — from Planning (recommended)**
1. Open the 🗺️ Planning tab
2. Enter your garden's coordinates
3. Click **Generate**
4. Plants load automatically into the Care Schedule

**Option B — manual CSV upload**
1. Download the template from the ⬇️ Template tab
2. Fill in the `name` and `sun_needed` columns (required)
3. Upload the file via the sidebar

### CSV format reference

| Column | Required | Values | Example |
|---|---|---|---|
| `name` | ✅ | free text | Lavender |
| `sun_needed` | ✅ | `full_sun` / `partial_shade` / `full_shade` | `full_sun` |
| `latin` | — | Latin genus and species | `Lavandula angustifolia` |
| `actual_sun` | — | same as sun_needed | `full_sun` |
| `soil` | — | `well_drained`, `moist`, `clay`, `sandy`, `rich` | `well_drained` |
| `is_bulb` | — | `yes` / `no` | `no` |
| `notes` | — | free text | |

If `pruning`, `feeding`, and `watering` columns are absent, they are filled automatically from the built-in database covering 60+ plant genera.

---

## Data sources

| Data | Source | Refresh |
|---|---|---|
| Weather forecast | [Open-Meteo API](https://open-meteo.com) | Hourly |
| Geocoding | Open-Meteo Geocoding API | On search |
| Plant database | PFAF (Plants for a Future) | Built-in |
| Climate projections | IPCC data | Built-in |
| Care instructions | Botanical care database — 60+ genera | Built-in |

An internet connection is required only for live weather and geocoding. Everything else runs locally.

---

## Adding plants to the care database

The care database lives in the `CARE_DB` dictionary in `gradinata_app.py`. To add a new genus:

```python
"Ficus": {
    "pruning": "Feb–Mar: light shape only. Avoid heavy pruning.",
    "feeding": "Apr–Aug: balanced liquid feed monthly.",
    "watering": "Keep moist spring–autumn. Reduce watering in winter.",
    "pruning_months": "2,3",
    "feeding_months": "4,5,6,7,8",
    "water_freq": "moderate",
},
```

The key is the Latin genus name (first word of the Latin plant name only).

---

## Dependencies

```
streamlit >= 1.28
pandas >= 2.0
pillow >= 10.0
openpyxl >= 3.1
```

---

## License

© 2025 Dantara Software EOOD. All rights reserved.

Open-Meteo data is used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
PFAF data is used for educational purposes.
