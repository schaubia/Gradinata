"""
🌿 Gradinata — Smart Garden Assistant
======================================
Consolidated app combining garden_plan + garden_org into one product.

Required files (place in the same folder):
  gradinata_app.py          ← this file
  garden_planner_core.py    ← from the original garden_plan project
  climate_projection.py     ← from the original garden_plan project

Run with:
  streamlit run gradinata_app.py
"""

# ── Imports ───────────────────────────────────────────────────────────────────
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import os
import sys
import io
import urllib.request
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))

# Try to load garden_plan modules — if missing, Planning / Climate / Grid tabs
# show a clear message; all other tabs work fine without them.
try:
    from garden_planner_core import GardenPlanner, PlantClusteringModule, Config
    from climate_projection import get_climate_projection_for_location
    PLANNER_AVAILABLE = True
except ImportError:
    PLANNER_AVAILABLE = False

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🌿 Gradinata",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=Jost:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'Jost', sans-serif; background: #f5f2eb; }
h1, h2, h3 { font-family: 'Cormorant Garamond', serif !important; }
.stButton > button { background:#3d6b1e; color:white; border:none; border-radius:6px;
    font-family:'Jost',sans-serif; font-weight:500; }
.stButton > button:hover { background:#2c5015; }
.stButton > button[kind="secondary"] { background:#e8e4dc; color:#2c3e1a; }
.app-header { background:linear-gradient(120deg,#1a3a0e 0%,#3d6b1e 60%,#6b8f4e 100%);
    color:white; border-radius:14px; padding:18px 28px; margin-bottom:20px; }
.app-header h1 { color:white !important; font-size:2rem; margin:0; }
.app-header p  { color:rgba(255,255,255,0.75); margin:4px 0 0; font-size:0.95rem; }
.wx-bar { background:linear-gradient(120deg,#1a3a0e 0%,#3d6b1e 60%,#6b8f4e 100%);
    color:white; border-radius:14px; padding:18px 28px; display:flex; gap:32px;
    align-items:center; flex-wrap:wrap; margin-bottom:24px; }
.wx-item { text-align:center; }
.wx-val  { font-size:1.6rem; font-weight:600; font-family:'Cormorant Garamond',serif; }
.wx-lbl  { font-size:0.72rem; opacity:0.75; letter-spacing:0.08em; text-transform:uppercase; }
.wx-alert { background:rgba(255,255,255,0.15); border-radius:8px; padding:8px 14px;
    font-size:0.85rem; border-left:3px solid #f0c040; }
.sec-hdr  { font-family:'Cormorant Garamond',serif; font-size:1.35rem; color:#1a3a0e;
    border-bottom:2px solid #d4e6c0; padding-bottom:5px; margin:20px 0 14px 0; }
.care-card  { border-radius:10px; padding:13px 16px; margin-bottom:6px; }
.care-title { font-weight:600; font-size:0.85rem; margin-bottom:4px; }
.care-body  { font-size:0.84rem; color:#333; line-height:1.58; }
.mismatch-card { background:#fff4e6; border-left:5px solid #e67e22; border-radius:8px;
    padding:12px 16px; margin-bottom:8px; }
.mismatch-card.severe { background:#fdecea; border-left-color:#c0392b; }
.mismatch-name { font-family:'Cormorant Garamond',serif; font-size:1.05rem;
    font-weight:700; color:#1a3a0e; }
.mismatch-body { font-size:0.85rem; color:#555; margin-top:4px; line-height:1.5; }
.plant-card { background-color:#F1F8F4; padding:1rem; border-radius:10px;
    border-left:4px solid #2E7D32; margin:0.5rem 0; }
.metric-container { background-color:#E8F5E9; padding:0.5rem; border-radius:5px; text-align:center; }
.download-section { background-color:#F5F5F5; padding:1.5rem; border-radius:10px; margin:1rem 0; }
.climate-info { background-color:#E3F2FD; border-left:4px solid #2196F3;
    padding:1rem; border-radius:5px; margin:1rem 0; }
.cluster-badge { display:inline-block; padding:0.15rem 0.5rem; border-radius:10px;
    font-size:0.75rem; font-weight:bold; margin-right:4px; }
.bridge-banner { background:#e8f5e9; border:1.5px solid #a5d6a7; border-radius:10px;
    padding:12px 16px; margin-bottom:16px; font-size:0.88rem; color:#1a5226; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
WMO = {
    0:"Clear sky", 1:"Mainly clear", 2:"Partly cloudy", 3:"Overcast", 45:"Foggy",
    51:"Light drizzle", 53:"Drizzle", 61:"Slight rain", 63:"Rain", 65:"Heavy rain",
    71:"Slight snow", 73:"Snow", 80:"Rain showers", 82:"Violent showers", 95:"Thunderstorm",
}
SUN_OPTIONS = {
    "full_sun":      "☀️ Full sun",
    "partial_shade": "⛅ Partial shade",
    "full_shade":    "🌑 Full shade",
}
SUN_NORM = {
    "full_sun":"full_sun", "full sun":"full_sun",
    "partial_shade":"partial_shade", "partial sun":"partial_shade",
    "partial shade":"partial_shade", "half shade":"partial_shade", "half_shade":"partial_shade",
    "full_shade":"full_shade", "full shade":"full_shade", "shade":"full_shade",
    "f":"full_sun", "s":"partial_shade", "n":"full_shade",
}
MONTH_NAMES = {
    1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
    7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec",
}
CLUSTER_COLORS = [
    "#4A7C59","#7B5EA7","#C07020","#2271B3","#C0392B",
    "#1A7A6A","#8B6340","#5C7A2A","#B03060","#2C5F8A",
]
FIELD_EXPLANATIONS = {
    "Shade":    {"F":"Full Sun","S":"Semi-Shade","N":"Full Shade"},
    "Moisture": {"D":"Dry","M":"Moist","We":"Wet","Wa":"Aquatic"},
    "Soil":     {"L":"Sandy","M":"Loamy","H":"Clay","acid":"Acidic","neutral":"Neutral","alkaline":"Alkaline"},
}

# ── Care database ─────────────────────────────────────────────────────────────
CARE_DB = {
    "Juglans":    {"pruning":"Late winter (Feb–Mar): remove dead/crossing branches. Avoid cutting in spring — bleeds sap.","feeding":"Apr: compost mulch around base. Jun: liquid seaweed once.","watering":"Deep water weekly in dry summers. Drought-tolerant once established.","pruning_months":"2,3","feeding_months":"4,6","water_freq":"weekly_summer"},
    "Cornus":     {"pruning":"Mar: cut coloured-stem varieties hard to ground for bright new growth.","feeding":"Apr: worm castings around base. Jun: compost tea.","watering":"Moderate. Water in dry spells, especially first 2 years.","pruning_months":"3","feeding_months":"4,6","water_freq":"moderate"},
    "Mespilus":   {"pruning":"Feb–Mar: thin canopy, remove inward growth.","feeding":"Apr: balanced compost. No high-nitrogen.","watering":"Drought-tolerant when established. Water young trees weekly.","pruning_months":"2,3","feeding_months":"4","water_freq":"low"},
    "Ginkgo":     {"pruning":"Nov–Feb: remove dead wood only. Minimal pruning needed.","feeding":"Apr: slow-release organic fertiliser once a year.","watering":"Drought-tolerant. Water weekly first season only.","pruning_months":"11,12,1,2","feeding_months":"4","water_freq":"low"},
    "Cydonia":    {"pruning":"Feb–Mar: open up centre for airflow and light.","feeding":"Mar: compost mulch. May: liquid seaweed.","watering":"Water well during fruit development (Jun–Aug).","pruning_months":"2,3","feeding_months":"3,5","water_freq":"moderate"},
    "Crataegus":  {"pruning":"Feb–Mar or after flowering (Jun): shape and thin.","feeding":"Apr: light compost mulch.","watering":"Very drought-tolerant. Water only in extreme heat.","pruning_months":"2,3,6","feeding_months":"4","water_freq":"low"},
    "Cotoneaster":{"pruning":"Mar or Aug: light trim for shape.","feeding":"Apr: compost mulch once.","watering":"Drought-tolerant. Water young plants in dry spells.","pruning_months":"3,8","feeding_months":"4","water_freq":"low"},
    "Corylus":    {"pruning":"Feb–Mar: remove oldest stems at base every 3 years for rejuvenation.","feeding":"Mar: compost mulch. May: seaweed foliar spray.","watering":"Moderate. Water in dry spells.","pruning_months":"2,3","feeding_months":"3,5","water_freq":"moderate"},
    "Salvia":     {"pruning":"Mar–Apr: cut back by 1/3 after winter. Deadhead through summer.","feeding":"Apr: worm castings. Avoid high nitrogen — reduces aroma.","watering":"Drought-tolerant. Water deeply once a week in summer.","pruning_months":"3,4","feeding_months":"4","water_freq":"weekly_summer"},
    "Thymus":     {"pruning":"Apr–May: light trim after flowering to keep compact. Never cut old wood.","feeding":"Apr: light compost. Very low feeder.","watering":"Very drought-tolerant. Overwatering is the main killer.","pruning_months":"4,5","feeding_months":"4","water_freq":"very_low"},
    "Melissa":    {"pruning":"Jun: cut to ground after first flowering — promotes fresh flush. Cut again in Aug.","feeding":"Apr: compost mulch. May: diluted nettle tea.","watering":"Moderate. Keep moist but not waterlogged.","pruning_months":"6,8","feeding_months":"4,5","water_freq":"moderate"},
    "Mentha":     {"pruning":"Jun and Aug: cut hard to ground to prevent flowering and keep bushy.","feeding":"May: nettle tea or compost tea monthly.","watering":"Keep consistently moist. Dries out fast in containers.","pruning_months":"6,8","feeding_months":"5,6,7,8","water_freq":"high"},
    "Parthenocissus":{"pruning":"Mar: cut back hard from gutters/windows. Shape in Aug if needed.","feeding":"Apr: compost mulch at base. Jun: liquid seaweed.","watering":"Moderate. Self-sufficient once established.","pruning_months":"3,8","feeding_months":"4,6","water_freq":"low"},
    "Lonicera":   {"pruning":"Mar: remove 1/3 oldest stems. Tidy after flowering (Jun).","feeding":"Apr: compost mulch. Jun: balanced liquid feed.","watering":"Moderate. Keep moist in summer.","pruning_months":"3,6","feeding_months":"4,6","water_freq":"moderate"},
    "Hedera":     {"pruning":"Mar–Apr: cut back hard if overgrown. Light trim any time.","feeding":"Apr: balanced compost. Tolerates poor soil.","watering":"Drought-tolerant once established. Water young plants regularly.","pruning_months":"3,4","feeding_months":"4","water_freq":"low"},
    "Clematis":   {"pruning":"Feb–Mar (Group 3): cut hard to 30cm from ground. Check your variety group.","feeding":"Mar: worm castings. Apr–Jul: liquid seaweed every 2 weeks.","watering":"Keep roots cool and moist. Mulch heavily. Water 2× week in summer.","pruning_months":"2,3","feeding_months":"3,4,5,6,7","water_freq":"moderate"},
    "Jasminum":   {"pruning":"After flowering (Aug–Sep): thin out oldest stems by 1/3.","feeding":"Apr: balanced compost. Jun: liquid seaweed.","watering":"Moderate. Drought-tolerant when established.","pruning_months":"8,9","feeding_months":"4,6","water_freq":"moderate"},
    "Viburnum":   {"pruning":"After flowering (Jun–Jul): light shaping only.","feeding":"Apr: compost mulch. Jun: liquid seaweed.","watering":"Moderate. Water in dry spells, especially in flower.","pruning_months":"6,7","feeding_months":"4,6","water_freq":"moderate"},
    "Pyracantha": {"pruning":"Apr: trim new growth back to 2–3 leaves. Aug: repeat light trim.","feeding":"Mar: compost mulch. Avoid high nitrogen — reduces berries.","watering":"Moderate once established. Water young plants weekly.","pruning_months":"4,8","feeding_months":"3","water_freq":"moderate"},
    "Rosa":       {"pruning":"Mar: main prune — cut to outward-facing bud, remove dead wood. Deadhead Jun–Sep.","feeding":"Mar: worm castings. May & Jul: high-potassium seaweed feed. Stop feeding Jul.","watering":"Deep water twice weekly in summer. Avoid wetting foliage.","pruning_months":"3,6,7,8,9","feeding_months":"3,5,7","water_freq":"twice_weekly_summer"},
    "Hydrangea":  {"pruning":"Mar: remove old flowerheads to first pair of fat buds. Don't prune in autumn.","feeding":"Apr: high-potassium feed. Jun: liquid seaweed.","watering":"Keep consistently moist. Water daily in summer heat.","pruning_months":"3","feeding_months":"4,6","water_freq":"daily_summer"},
    "Hosta":      {"pruning":"Oct–Nov: cut all foliage to ground after frost. Mar: remove slug-damaged leaves.","feeding":"Apr: slow-release balanced feed or worm castings.","watering":"Keep consistently moist. Water 3× week in summer.","pruning_months":"3,10,11","feeding_months":"4","water_freq":"high_summer"},
    "Paeonia":    {"pruning":"Oct–Nov: cut stems to 10cm after frost. Do not cut in spring — harms flowering.","feeding":"Mar: worm castings. May: seaweed after flowering.","watering":"Deep weekly watering in May–Jun. Drought-tolerant after.","pruning_months":"10,11","feeding_months":"3,5","water_freq":"weekly_flowering"},
    "Echinacea":  {"pruning":"Mar: cut old stems to ground. Leave seed heads over winter for birds.","feeding":"Apr: worm castings. Jun: compost tea.","watering":"Drought-tolerant once established. Water weekly first season.","pruning_months":"3","feeding_months":"4,6","water_freq":"low"},
    "Lavandula":  {"pruning":"Aug–Sep: cut back flowered stems by 2/3. Mar: light tidy. Never cut old wood.","feeding":"Apr: light compost. Very low feeder — rich soil reduces aroma.","watering":"Very drought-tolerant. Overwatering kills lavender.","pruning_months":"3,8,9","feeding_months":"4","water_freq":"very_low"},
    "Dahlia":     {"pruning":"Deadhead regularly Jun–Oct. Cut to ground after first frost (Oct–Nov).","feeding":"Jun: high-potassium feed every 2 weeks until Sep.","watering":"Water deeply 2× week in summer. Keep evenly moist.","pruning_months":"6,7,8,9,10","feeding_months":"6,7,8,9","water_freq":"twice_weekly_summer"},
    "Iris":       {"pruning":"After flowering (Jun–Jul): cut flower stems. Tidy fans in Sep.","feeding":"Mar: low-nitrogen fertiliser. May: high-potassium after flowering.","watering":"Moderate during growth. Dry in summer — rhizomes need sun to bake.","pruning_months":"6,7,9","feeding_months":"3,5","water_freq":"low_summer"},
    "Prunus":     {"pruning":"Mar–Apr: trim after flowering. Hard prune if overgrown.","feeding":"Apr: compost mulch. Jun: balanced liquid feed.","watering":"Moderate. Water young plants regularly.","pruning_months":"3,4","feeding_months":"4,6","water_freq":"moderate"},
    "Pinus":      {"pruning":"May–Jun: pinch back candles by 1/2 to control size. No hard pruning.","feeding":"Apr: slow-release conifer food once.","watering":"Drought-tolerant. Water young plants only.","pruning_months":"5,6","feeding_months":"4","water_freq":"low"},
    "Berberis":   {"pruning":"After flowering (Jun): remove oldest stems. Wear gloves — thorns.","feeding":"Apr: compost mulch.","watering":"Very drought-tolerant.","pruning_months":"6","feeding_months":"4","water_freq":"low"},
    "Spiraea":    {"pruning":"Mar: cut hard to ground. After flowering (Jul): deadhead.","feeding":"Apr: balanced compost.","watering":"Moderate.","pruning_months":"3,7","feeding_months":"4","water_freq":"moderate"},
    "Weigela":    {"pruning":"After flowering (Jun–Jul): remove 1/3 oldest stems at base.","feeding":"Apr: compost mulch. Jun: liquid seaweed.","watering":"Moderate. Water during dry spells.","pruning_months":"6,7","feeding_months":"4,6","water_freq":"moderate"},
}
DEFAULT_CARE = {
    "pruning":        "Mar: general tidy — remove dead/damaged stems.",
    "feeding":        "Apr: worm castings or compost mulch. Jun: liquid seaweed.",
    "watering":       "Water moderately during dry periods, especially summer.",
    "pruning_months": "3",
    "feeding_months": "4,6",
    "water_freq":     "moderate",
}

# ── Helper functions ──────────────────────────────────────────────────────────

def lookup_care(latin):
    if not latin or str(latin).lower() in ("nan","none",""):
        return DEFAULT_CARE
    for genus, care in CARE_DB.items():
        if genus.lower() in str(latin).lower():
            return care
    return DEFAULT_CARE


def months_list(months_str):
    if not months_str or str(months_str).lower() in ("nan","none",""):
        return []
    try:
        return [int(m.strip()) for m in str(months_str).split(",") if m.strip()]
    except Exception:
        return []


def tasks_this_month(df, month):
    tasks = []
    for _, row in df.iterrows():
        name = row["name"]
        care = lookup_care(row.get("latin"))
        if month in months_list(row.get("pruning_months") or care["pruning_months"]):
            tasks.append((name, "✂️ Pruning", row.get("pruning") or care["pruning"]))
        if month in months_list(row.get("feeding_months") or care["feeding_months"]):
            tasks.append((name, "🌿 Feeding", row.get("feeding") or care["feeding"]))
        if row.get("is_bulb") and month in [10, 11]:
            tasks.append((name, "🫙 Bulb care", f"Check if {name} bulbs need lifting before first frost."))
        if row.get("is_bulb") and month in [3, 4]:
            tasks.append((name, "🌱 Bulb planting", f"Check if {name} bulbs/corms are ready to plant out."))
    return tasks


def sun_mismatch(needed, actual):
    order = ["full_shade","partial_shade","full_sun"]
    if not needed or not actual or needed not in order or actual not in order:
        return None
    diff = order.index(actual) - order.index(needed)
    if diff >= 1: return "over"
    if diff <= -1: return "under"
    return None


def render_tasks_by_type(tasks, month_name=""):
    grouped = defaultdict(list)
    for name, task_type, desc in tasks:
        grouped[task_type].append((name, desc))
    TYPE_STYLE = {
        "✂️ Pruning":       ("#eaf2e0","#2c5015"),
        "🌿 Feeding":       ("#f0f7e8","#1a5226"),
        "💧 Watering":      ("#e8f3fb","#1a3a5c"),
        "🫙 Bulb care":     ("#fef9e8","#5c4a00"),
        "🌱 Bulb planting": ("#f3eeff","#3a1a7a"),
    }
    active_types = [t for t in TYPE_STYLE if t in grouped]
    if not active_types:
        st.success(f"✅ No scheduled tasks{' for ' + month_name if month_name else ''}.")
        return
    cols = st.columns(len(active_types))
    for col, task_type in zip(cols, active_types):
        bg, fg = TYPE_STYLE[task_type]
        rows_html = "".join(
            f'<tr><td style="padding:7px 10px;border-bottom:1px solid {bg};font-weight:600;'
            f'color:#1a3a0e;font-size:0.85rem;vertical-align:top;width:35%">{name}</td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid {bg};color:#444;'
            f'font-size:0.82rem;line-height:1.5;vertical-align:top">{desc}</td></tr>'
            for name, desc in grouped[task_type]
        )
        col.markdown(f'''
        <div style="background:{bg};border-radius:10px;overflow:hidden;height:100%">
          <div style="background:{fg};color:white;padding:10px 14px;font-weight:600;
                      font-size:0.95rem;font-family:Cormorant Garamond,serif">
            {task_type} <span style="opacity:0.75;font-size:0.8rem;font-weight:400">
              ({len(grouped[task_type])} plant{"s" if len(grouped[task_type])>1 else ""})</span>
          </div>
          <table style="width:100%;border-collapse:collapse">{rows_html}</table>
        </div>''', unsafe_allow_html=True)


def require_plants() -> bool:
    """Returns True if plants are loaded, False (with info message) if not."""
    if st.session_state.plants_df is None:
        st.info("📂 Upload your plant list via the sidebar, or generate plants from the **🗺️ Planning** tab first.")
        return False
    return True


# ── THE BRIDGE: Convert garden_plan results → garden_org plants_df ────────────
def sync_plan_to_care(recommendations_df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts a GardenPlanner recommendations DataFrame into the format
    expected by the care schedule module.
    This is the key connection between the two original projects.
    """
    rows = []
    for _, row in recommendations_df.iterrows():
        latin = str(row.get("latin_name", row.get("Latin Name",
                    row.get("Species", row.get("species", "")))))
        name  = str(row.get("common_name", row.get("Common Name",
                    row.get("Name", latin))))
        shade_raw  = str(row.get("shade", row.get("Shade", "F"))).strip()
        sun_needed = SUN_NORM.get(shade_raw.lower(), "full_sun")
        soil_raw   = str(row.get("soil", row.get("Soil", ""))).strip()
        care       = lookup_care(latin)
        score      = row.get("score", row.get("Score", None))
        rows.append({
            "name":           name,
            "latin":          latin,
            "sun_needed":     sun_needed,
            "actual_sun":     None,
            "soil":           soil_raw if soil_raw not in ("","nan") else None,
            "is_bulb":        False,
            "notes":          f"Score: {score:.2f}" if score else "",
            "pruning":        care["pruning"],
            "feeding":        care["feeding"],
            "watering":       care["watering"],
            "pruning_months": care["pruning_months"],
            "feeding_months": care["feeding_months"],
            "water_freq":     care["water_freq"],
        })
    return pd.DataFrame(rows) if rows else None


# ── Weather helpers ───────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def geocode_location(city_name: str):
    url = (f"https://geocoding-api.open-meteo.com/v1/search"
           f"?name={urllib.parse.quote(city_name)}&count=1&language=en&format=json")
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Gradinata/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        if not data.get("results"):
            return {"error": f"Location '{city_name}' not found."}
        r = data["results"][0]
        return {"name":r["name"],"country":r.get("country",""),"region":r.get("admin1",""),
                "lat":r["latitude"],"lon":r["longitude"],
                "timezone":r.get("timezone","UTC"),"elevation":r.get("elevation",0)}
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=3600)
def fetch_weather(lat: float, lon: float, timezone: str):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,uv_index_max,weathercode"
           f"&current_weather=true&timezone={urllib.parse.quote(timezone)}&forecast_days=7")
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Gradinata/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def parse_weather(raw):
    if "error" in raw: return {"ok": False}
    try:
        cw = raw["current_weather"]; d = raw["daily"]
        mins = d["temperature_2m_min"]; maxs = d["temperature_2m_max"]
        rain = d["precipitation_sum"]; uv = d["uv_index_max"]
        codes = d["weathercode"]; dates = d["time"]
        return {"ok":True,"temp_now":cw["temperature"],"desc_now":WMO.get(cw["weathercode"],"Unknown"),
                "temp_max":maxs[0],"temp_min":mins[0],"uv":uv[0],"rain_today":rain[0],
                "weekly_rain":sum(rain),"frost_risk":any(t<=0 for t in mins),
                "frost_days":[dates[i] for i,t in enumerate(mins) if t<=0],
                "soil_dry":sum(rain)<5 and sum(maxs)/len(maxs)>15,
                "heavy_rain":any(r>=10 for r in rain),
                "dates":dates,"mins":mins,"maxs":maxs,"rain":rain,"uv_all":uv,"codes":codes}
    except Exception:
        return {"ok": False}


# ── CSV upload parser ─────────────────────────────────────────────────────────
def parse_upload(f):
    try:
        nm = f.name.lower()
        df = pd.read_csv(f) if nm.endswith(".csv") else pd.read_excel(f)
        df.columns = [c.strip().lower().replace(" ","_") for c in df.columns]
        df = df.where(pd.notna(df), None)
        if "sun_needed" in df.columns: sun_col = "sun_needed"
        elif "sun" in df.columns: sun_col = "sun"
        else: return None, "File must contain a 'sun_needed' or 'sun' column."
        df["sun_needed"] = df[sun_col].astype(str).str.strip().str.lower().map(SUN_NORM)
        if "name" not in df.columns: return None, "File must contain a 'name' column."
        df["name"] = df["name"].astype(str).str.strip()
        for col in ["latin","soil","notes","actual_sun","pruning","feeding","watering",
                    "pruning_months","feeding_months","water_freq"]:
            if col not in df.columns: df[col] = None
        df["is_bulb"] = df.get("is_bulb", pd.Series([False]*len(df))).apply(
            lambda x: str(x).strip().lower() in ("yes","true","1") if x else False)
        for i, row in df.iterrows():
            if not row.get("pruning"):
                care = lookup_care(row.get("latin"))
                for k in ["pruning","feeding","watering","pruning_months","feeding_months","water_freq"]:
                    df.at[i, k] = care[k]
        return df, ""
    except Exception as e:
        return None, str(e)


# ── garden_plan helpers ───────────────────────────────────────────────────────
def cluster_color(cluster_id):
    return CLUSTER_COLORS[int(cluster_id) % len(CLUSTER_COLORS)]


def pick_emoji(name, habit="", edibility=""):
    n = str(name).lower()
    mapping = {"rose":"🌹","sunflower":"🌻","lavender":"💜","mint":"🌿","basil":"🌿",
               "tomato":"🍅","carrot":"🥕","lettuce":"🥬","strawberr":"🍓","pea":"🫛",
               "apple":"🍎","pear":"🍐","cherry":"🍒","grape":"🍇","bean":"🫘"}
    for key, emoji in mapping.items():
        if key in n: return emoji
    h = str(habit).lower()
    if "tree" in h: return "🌳"
    if "shrub" in h: return "🌲"
    return "🌱"


def add_legend_to_image(image_path):
    try:
        img = Image.open(image_path)
        new_img = Image.new("RGB", (img.width, img.height + 100), "white")
        new_img.paste(img, (0, 0))
        draw = ImageDraw.Draw(new_img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except Exception:
            font = ImageFont.load_default()
        draw.text((20, img.height + 20), "Gradinata — Plant Clustering", font=font, fill="#2E7D32")
        buf = io.BytesIO()
        new_img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception:
        with open(image_path, "rb") as f:
            return io.BytesIO(f.read())


# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [
    ("plants_df",          None),
    ("plants_from_plan",   False),
    ("wx",                 None),
    ("location",           {"name":"Sofia","country":"Bulgaria","region":"Sofia-Capital",
                            "lat":42.698,"lon":23.322,"timezone":"Europe/Sofia","elevation":550}),
    ("climate_desc",       "continental (cold winters with frost, hot dry summers)"),
    ("planner_results",    None),
    ("planner_df",         None),
    ("climate_projection", None),
    ("garden_name",        "My Garden"),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <h1>🌿 Gradinata</h1>
  <p>Smart Garden Assistant — plan, care, and grow smarter</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌿 Gradinata")
    loc = st.session_state.location
    st.caption(f"📍 {loc['name']}, {loc['country']}")
    st.divider()

    plant_count = len(st.session_state.plants_df) if st.session_state.plants_df is not None else 0
    if plant_count:
        source_label = "from Planning" if st.session_state.plants_from_plan else "from CSV"
        st.success(f"✅ {plant_count} plants loaded ({source_label})")
        if st.button("↩️ Clear plant list", use_container_width=True):
            st.session_state.plants_df = None
            st.session_state.plants_from_plan = False
            st.rerun()
    else:
        st.markdown("**📂 Load your plants:**")
        sb_file = st.file_uploader("CSV or XLSX", type=["csv","xlsx","xls"],
                                   key="sidebar_uploader", label_visibility="collapsed")
        if sb_file:
            parsed, err = parse_upload(sb_file)
            if err:
                st.error(f"❌ {err}")
            else:
                st.session_state.plants_df = parsed
                st.session_state.plants_from_plan = False
                st.rerun()
        st.caption("or generate from the **🗺️ Planning** tab")
    st.divider()

    with st.expander("📍 Change location"):
        city_input = st.text_input("City", placeholder="e.g. London, Sofia, Paris…", key="city_input")
        if st.button("🔍 Search", use_container_width=True) and city_input:
            with st.spinner(f"Searching for {city_input}…"):
                geo = geocode_location(city_input)
                if "error" in geo:
                    st.error(geo["error"])
                else:
                    st.session_state.location = geo
                    st.session_state.wx = None
                    st.rerun()

    if st.button("🔄 Refresh weather", use_container_width=True):
        st.cache_data.clear()
        st.session_state.wx = None

    loc = st.session_state.location
    if st.session_state.wx is None:
        with st.spinner(f"Loading weather for {loc['name']}…"):
            raw = fetch_weather(loc["lat"], loc["lon"], loc["timezone"])
            st.session_state.wx = parse_weather(raw)

    wx_s = st.session_state.wx
    if wx_s and wx_s.get("ok"):
        st.markdown(f"**{wx_s['temp_now']}°C** · {wx_s['desc_now']}")
        st.caption(f"↑{wx_s['temp_max']}° ↓{wx_s['temp_min']}° · UV {wx_s['uv']}")
        if wx_s["frost_risk"]:
            st.warning(f"❄️ Frost: {', '.join(wx_s['frost_days'])}")
    else:
        st.caption("Weather unavailable")

    st.divider()
    today = st.date_input("📅 Date", value=date.today())

# ── Main tabs ─────────────────────────────────────────────────────────────────
tab_plan, tab_dash, tab_care, tab_sun, tab_grid, tab_climate, tab_template = st.tabs([
    "🗺️ Planning",
    "🌤️ Dashboard",
    "📋 Care Schedule",
    "☀️ Sun Setup",
    "📐 Garden Grid",
    "🌍 Climate",
    "⬇️ Template",
])

wx = st.session_state.wx or {"ok": False}
df = st.session_state.plants_df

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PLANNING
# ══════════════════════════════════════════════════════════════════════════════
with tab_plan:
    if not PLANNER_AVAILABLE:
        st.warning("""
        ⚠️ **Planning modules not found.**

        To enable this tab, place these files in the same folder as `gradinata_app.py`:
        - `garden_planner_core.py`
        - `climate_projection.py`

        The other tabs (Dashboard, Care Schedule, Sun Setup, Template) work without them —
        just upload a CSV via the sidebar.
        """)

    if PLANNER_AVAILABLE:
        st.markdown("# 🗺️ Garden Planning")
    st.caption("Generate personalised plant recommendations based on your location's real climate and soil data.")

    with st.expander("⚙️ Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            garden_name = st.text_input("Garden name", value=st.session_state.garden_name)
            latitude    = st.number_input("Latitude", value=loc["lat"], format="%.4f",
                                          min_value=-90.0, max_value=90.0)
            longitude   = st.number_input("Longitude", value=loc["lon"], format="%.4f",
                                          min_value=-180.0, max_value=180.0)
            st.caption("💡 Right-click on Google Maps and copy the coordinates")
        with col2:
            num_rec     = st.slider("Number of plants", 10, 100, 30, 10)
            min_score   = st.slider("Minimum suitability", 0.0, 1.0, 0.5, 0.05)
            max_cluster = st.slider("Plants per cluster", 3, 10, 5, 1)

    col_gen, col_reset = st.columns(2)
    generate = col_gen.button("🌿 Generate", type="primary", use_container_width=True)
    if col_reset.button("🔄 Reset", use_container_width=True):
        for k in ["planner_results","planner_df","climate_projection","plants_df"]:
            st.session_state[k] = None
        st.session_state.plants_from_plan = False
        st.rerun()

    if generate:
        st.session_state.garden_name = garden_name
        with st.spinner("🌍 Analysing climate and soil data…"):
            try:
                planner = GardenPlanner(Config())
                results = planner.generate_recommendations(
                    latitude=latitude, longitude=longitude,
                    num_recommendations=num_rec, min_suitability_score=min_score,
                )
                st.session_state.planner_results = results
                df_plan = results.get("recommendations")
                if df_plan is not None and not df_plan.empty:
                    try:
                        clustering = PlantClusteringModule(max_cluster_size=max_cluster)
                        df_plan = clustering.cluster_plants(df_plan)
                    except Exception:
                        pass
                    st.session_state.planner_df = df_plan
                    # ── THE BRIDGE ──────────────────────────────────────────
                    care_df = sync_plan_to_care(df_plan)
                    if care_df is not None:
                        st.session_state.plants_df = care_df
                        st.session_state.plants_from_plan = True
                    try:
                        proj = get_climate_projection_for_location(latitude, longitude)
                        st.session_state.climate_projection = proj
                    except Exception:
                        st.session_state.climate_projection = None
                    st.success(f"✅ {len(df_plan)} plants generated and loaded into **Care Schedule**!")
            except Exception as e:
                st.error(f"❌ Error: {e}")

    if st.session_state.planner_df is not None:
        plan_df = st.session_state.planner_df
        if st.session_state.plants_from_plan:
            st.markdown("""<div class="bridge-banner">
              🔗 <strong>Automatically synced:</strong> these plants are now loaded in
              <strong>🌤️ Dashboard</strong> and <strong>📋 Care Schedule</strong> with full care instructions.
            </div>""", unsafe_allow_html=True)

        st.divider()
        score_col = next((c for c in plan_df.columns if "score" in c.lower()), None)
        if st.session_state.climate_projection:
            proj = st.session_state.climate_projection
            p = proj.get("projection") if isinstance(proj, dict) else proj
            if p:
                impact = getattr(p, "impact_level", "moderate")
                impact_color = {"low":"#2e7d32","moderate":"#e65100","high":"#b71c1c"}.get(impact,"#555")
                st.markdown(f"""<div class="climate-info">
                  🌍 <strong>Climate projection</strong> · Impact level:
                  <span style="color:{impact_color};font-weight:600">{impact.upper()}</span>
                </div>""", unsafe_allow_html=True)

        st.markdown(f'<div class="sec-hdr">🌱 {len(plan_df)} recommended plants</div>', unsafe_allow_html=True)
        name_col  = next((c for c in plan_df.columns if "name" in c.lower() and "latin" not in c.lower()), plan_df.columns[0])
        latin_col = next((c for c in plan_df.columns if "latin" in c.lower() or "species" in c.lower()), None)

        for _, row in plan_df.iterrows():
            name  = str(row.get(name_col,""))
            latin = str(row.get(latin_col,"")) if latin_col else ""
            emoji = pick_emoji(name, row.get("growth_habit",""), row.get("edibility",""))
            score = float(row.get(score_col, 0)) if score_col else 0
            cluster_id = row.get("cluster_id", row.get("Cluster ID"))
            badge_html = ""
            if cluster_id is not None:
                cc = cluster_color(cluster_id)
                badge_html = f'<span class="cluster-badge" style="background:{cc}22;color:{cc};border:1px solid {cc}55">Cluster {cluster_id}</span>'
            with st.expander(f"{emoji} **{name}** {'— '+latin if latin and latin != 'nan' else ''}"):
                c1, c2 = st.columns([3, 1])
                with c1:
                    shade_desc    = FIELD_EXPLANATIONS["Shade"].get(str(row.get("shade","")).strip(),"")
                    moisture_desc = FIELD_EXPLANATIONS["Moisture"].get(str(row.get("moisture","")).strip(),"")
                    if shade_desc:    st.caption(f"🌤️ {shade_desc}")
                    if moisture_desc: st.caption(f"💧 {moisture_desc}")
                    st.markdown(badge_html, unsafe_allow_html=True)
                with c2:
                    if score_col and score > 0:
                        color_score = "#2E7D32" if score>=0.8 else ("#558B2F" if score>=0.6 else "#FFA000")
                        label = "Excellent" if score>=0.8 else ("Good" if score>=0.6 else "Fair")
                        st.markdown(f"<div class='metric-container'><div style='font-size:1.8rem;color:{color_score};font-weight:bold'>{score:.2f}</div><div style='font-size:0.8rem;color:{color_score}'>{label}</div></div>",
                                    unsafe_allow_html=True)

        st.divider()
        st.markdown('<div class="download-section">', unsafe_allow_html=True)
        st.markdown("### 📥 Download your plan")
        dcol1, dcol2 = st.columns(2)
        with dcol1:
            st.download_button("📄 Plant list (CSV)", plan_df.to_csv(index=False).encode(),
                               file_name=f"{garden_name.replace(' ','_')}_plants.csv",
                               mime="text/csv", use_container_width=True)
        with dcol2:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                plan_df.to_excel(writer, index=False, sheet_name="Plants")
            st.download_button("📊 Full report (Excel)", buf.getvalue(),
                               file_name=f"{garden_name.replace(' ','_')}_report.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    st.markdown("# 🌤️ Dashboard")
    if wx.get("ok"):
        loc_d = st.session_state.location
        st.markdown(f"""<div class="wx-bar">
          <div class="wx-item"><div class="wx-val">{wx['temp_now']}°C</div><div class="wx-lbl">Now · {loc_d['name']}</div></div>
          <div class="wx-item"><div class="wx-val">{wx['temp_max']}° / {wx['temp_min']}°</div><div class="wx-lbl">Today</div></div>
          <div class="wx-item"><div class="wx-val">{wx['uv']}</div><div class="wx-lbl">UV Index</div></div>
          <div class="wx-item"><div class="wx-val">{wx['rain_today']} mm</div><div class="wx-lbl">Rain today</div></div>
          <div class="wx-item"><div class="wx-val">{wx['weekly_rain']:.0f} mm</div><div class="wx-lbl">7-day rain</div></div>
          <div class="wx-item"><div class="wx-val">{wx['desc_now']}</div><div class="wx-lbl">Conditions</div></div>
          <div class="wx-alert">{"❄️ Frost: "+', '.join(wx['frost_days']) if wx['frost_risk'] else '✅ No frost'} &nbsp;·&nbsp; {"💧 Watering needed" if wx['soil_dry'] else "🌧️ Soil OK"}</div>
        </div>""", unsafe_allow_html=True)
        cols7 = st.columns(7)
        for i, col in enumerate(cols7):
            dl   = datetime.strptime(wx["dates"][i],"%Y-%m-%d").strftime("%a %d")
            icon = "❄️" if wx["mins"][i]<=0 else ("🌧️" if wx["rain"][i]>5 else ("☀️" if wx["codes"][i]<=2 else "⛅"))
            col.markdown(f"**{dl}**"); col.markdown(f"{icon} {wx['maxs'][i]:.0f}°/{wx['mins'][i]:.0f}°")
            if wx["rain"][i]>0: col.caption(f"💧{wx['rain'][i]:.0f}mm")
    else:
        st.info("Weather unavailable — click 'Refresh weather' in the sidebar.")

    st.divider()
    if require_plants():
        df = st.session_state.plants_df
        n_set       = int((df["actual_sun"].notna() & (df["actual_sun"] != "")).sum())
        mismatches  = [(row, sun_mismatch(row.get("sun_needed"), row.get("actual_sun")))
                       for _, row in df.iterrows()
                       if sun_mismatch(row.get("sun_needed"), row.get("actual_sun"))]
        month_tasks = tasks_this_month(df, today.month)

        if st.session_state.plants_from_plan:
            st.markdown("""<div class="bridge-banner">
              🔗 Plants were generated from <strong>🗺️ Planning</strong>.
              Set sun positions in the <strong>☀️ Sun Setup</strong> tab for a full mismatch analysis.
            </div>""", unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🌱 Plants", len(df))
        c2.metric("☀️ Sun positions set", f"{n_set}/{len(df)}")
        c3.metric("⚠️ Mismatches", len(mismatches))
        c4.metric(f"📅 Tasks for {MONTH_NAMES[today.month]}", len(month_tasks))

        st.markdown(f'<div class="sec-hdr">📅 Tasks for {MONTH_NAMES[today.month]}</div>', unsafe_allow_html=True)
        render_tasks_by_type(month_tasks, MONTH_NAMES[today.month])

        col_l, col_r = st.columns(2)
        with col_l:
            if mismatches:
                st.markdown('<div class="sec-hdr">⚠️ Placement mismatches</div>', unsafe_allow_html=True)
                for row, mtype in mismatches:
                    needed = SUN_OPTIONS.get(str(row.get("sun_needed") or ""),"?")
                    actual = SUN_OPTIONS.get(str(row.get("actual_sun") or ""),"?")
                    msg = f"Gets <b>{actual}</b> but needs <b>{needed}</b> — {'too much sun.' if mtype=='over' else 'too little sun.'}"
                    st.markdown(f"""<div class="mismatch-card {'severe' if mtype=='over' else ''}">
                      <div class="mismatch-name">{row['name']}</div>
                      <div class="mismatch-body">{msg}</div></div>""", unsafe_allow_html=True)
        with col_r:
            if wx.get("ok"):
                st.markdown('<div class="sec-hdr">🔔 Weather alerts</div>', unsafe_allow_html=True)
                alerts = []
                if wx["frost_risk"]:  alerts.append("❄️ **Frost expected** — protect frost-sensitive plants.")
                if wx["soil_dry"]:    alerts.append("💧 **Soil is dry** — water deeply, morning or evening.")
                if wx["uv"] >= 7:     alerts.append("☀️ **High UV** — avoid transplanting. Water early.")
                if wx["heavy_rain"]:  alerts.append("🌧️ Heavy rain forecast — skip feeding this week.")
                if not alerts:        alerts.append("✅ No urgent alerts — a good week for routine tasks.")
                for a in alerts: st.markdown(f"- {a}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CARE SCHEDULE
# ══════════════════════════════════════════════════════════════════════════════
with tab_care:
    st.markdown("# 📋 Care Schedule")
    if require_plants():
        df = st.session_state.plants_df
    CARE_COLORS = {
        "pruning":  ("#eaf2e0","#2c5015","✂️ Pruning"),
        "feeding":  ("#f0f7e8","#1a5226","🌿 Feeding"),
        "watering": ("#e8f3fb","#1a3a5c","💧 Watering"),
    }
    view = st.radio("View", ["📅 By month","🌿 By plant","⚠️ Mismatches only"], horizontal=True)
    st.divider()

    if view == "📅 By month":
        month_sel = st.selectbox("Month", list(MONTH_NAMES.values()), index=today.month - 1)
        month_num = list(MONTH_NAMES.values()).index(month_sel) + 1
        tasks = tasks_this_month(df, month_num)
        if tasks: st.caption(f"**{len(tasks)} tasks** scheduled for {month_sel}")
        render_tasks_by_type(tasks, month_sel)

    elif view == "🌿 By plant":
        search  = st.text_input("🔍 Search plant", placeholder="Type name…")
        show_df = df[df["name"].str.contains(search, case=False, na=False)] if search else df
        for _, row in show_df.iterrows():
            mtype = sun_mismatch(row.get("sun_needed"), row.get("actual_sun"))
            warn  = "⚠️ " if mtype else ("✅ " if row.get("actual_sun") else "○ ")
            with st.expander(f"{warn}**{row['name']}**{'  🫙' if row.get('is_bulb') else ''} · {SUN_OPTIONS.get(str(row.get('sun_needed') or ''),'?')}"):
                if row.get("latin"): st.caption(f"*{row['latin']}*")
                for care_key, (bg, fg, title) in CARE_COLORS.items():
                    text = row.get(care_key) or lookup_care(row.get("latin"))[care_key]
                    month_key = care_key + "_months"
                    months_active = months_list(row.get(month_key) or lookup_care(row.get("latin")).get(month_key,""))
                    badge = (f" <span style='background:#3d6b1e;color:white;border-radius:10px;"
                             f"padding:1px 8px;font-size:0.72rem;'>📅 Due this month</span>"
                             if today.month in months_active else "")
                    st.markdown(f"""<div class="care-card" style="background:{bg}">
                      <div class="care-title" style="color:{fg}">{title}{badge}</div>
                      <div class="care-body">{text}</div></div>""", unsafe_allow_html=True)
                if mtype:
                    n_lbl = SUN_OPTIONS.get(str(row.get("sun_needed") or ""),"?")
                    a_lbl = SUN_OPTIONS.get(str(row.get("actual_sun") or ""),"?")
                    st.markdown(f"""<div class="care-card" style="background:#fdecea;border:1.5px solid #c0392b">
                      <div class="care-title" style="color:#c0392b">⚠️ Placement problem</div>
                      <div class="care-body">Gets <b>{a_lbl}</b> but needs <b>{n_lbl}</b> — {'too much sun.' if mtype=='over' else 'too little sun.'}</div>
                    </div>""", unsafe_allow_html=True)

    else:
        mismatch_df = df[df.apply(
            lambda r: sun_mismatch(r.get("sun_needed"), r.get("actual_sun")) is not None, axis=1)]
        if mismatch_df.empty:
            st.success("✅ All plants are correctly placed!")
        else:
            st.caption(f"**{len(mismatch_df)} plants** with placement issues")
            for _, row in mismatch_df.iterrows():
                mtype  = sun_mismatch(row.get("sun_needed"), row.get("actual_sun"))
                needed = SUN_OPTIONS.get(str(row.get("sun_needed") or ""),"?")
                actual = SUN_OPTIONS.get(str(row.get("actual_sun") or ""),"?")
                with st.expander(f"⚠️ **{row['name']}** — needs {needed}, gets {actual}"):
                    st.markdown(f"""<div class="care-card" style="background:#fdecea;border:1.5px solid #c0392b">
                      <div class="care-title" style="color:#c0392b">⚠️ Placement problem</div>
                      <div class="care-body">{"Too much sun — may scorch or dry out." if mtype=='over' else "Too little sun — likely poor flowering and weak growth."}</div>
                    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SUN SETUP
# ══════════════════════════════════════════════════════════════════════════════
with tab_sun:
    st.markdown("# ☀️ Sun Setup")
    st.caption("Tell the app how much sun each plant actually gets in its current spot.")
    if require_plants():
        bc1, bc2, bc3, bc4, bc5 = st.columns([2.5,1.2,1.5,1.3,1])
        bulk_q = bc1.text_input("Filter (empty = all)", placeholder="e.g. rose…", label_visibility="collapsed")
        mask   = (st.session_state.plants_df["name"].str.contains(bulk_q, case=False, na=False)
                  if bulk_q else pd.Series([True]*len(st.session_state.plants_df)))
        if bc2.button("☀️ Full sun"):    st.session_state.plants_df.loc[mask,"actual_sun"]="full_sun";    st.rerun()
        if bc3.button("⛅ Part. shade"): st.session_state.plants_df.loc[mask,"actual_sun"]="partial_shade"; st.rerun()
        if bc4.button("🌑 Full shade"):  st.session_state.plants_df.loc[mask,"actual_sun"]="full_shade";  st.rerun()
        if bc5.button("✕ Clear"):        st.session_state.plants_df.loc[mask,"actual_sun"]=None;          st.rerun()

        st.divider()
        show_f = st.radio("Show", ["All plants","⚠️ Mismatches only","○ Not set yet"], horizontal=True)

        for i, row in st.session_state.plants_df.iterrows():
            actual = row.get("actual_sun") or ""
            needed = row.get("sun_needed") or ""
            mtype  = sun_mismatch(needed, actual)
            if show_f == "⚠️ Mismatches only" and not mtype: continue
            if show_f == "○ Not set yet" and actual: continue

            status = "○" if not actual else ("⚠️" if mtype else "✅")
            color  = "#aaa" if not actual else ("#c0392b" if mtype else "#2c7a1e")
            actual_html = (f"<span style='color:{'#c0392b' if mtype else '#2c7a1e'};font-weight:600'>{SUN_OPTIONS.get(actual,'')}</span>"
                           if actual else "<span style='color:#bbb;font-size:0.82rem'>— not set —</span>")

            cn, cneeded, cactual, cb1, cb2, cb3 = st.columns([3,2,2,1.2,1.5,1.3])
            cn.markdown(
                f"<span style='color:{color};font-weight:600'>{status} {row['name']}</span>"
                f"<br><span style='font-size:0.75rem;color:#888'>{row.get('latin','')}</span>",
                unsafe_allow_html=True)
            cneeded.markdown(f"<span style='font-size:0.82rem;color:#555'>{SUN_OPTIONS.get(needed, needed or '—')}</span>",
                             unsafe_allow_html=True)
            cactual.markdown(actual_html, unsafe_allow_html=True)

            t = lambda v: "primary" if actual == v else "secondary"
            if cb1.button("☀️", key=f"fs_{i}",  type=t("full_sun")):
                st.session_state.plants_df.at[i,"actual_sun"] = None if actual=="full_sun" else "full_sun"; st.rerun()
            if cb2.button("⛅", key=f"ps_{i}",  type=t("partial_shade")):
                st.session_state.plants_df.at[i,"actual_sun"] = None if actual=="partial_shade" else "partial_shade"; st.rerun()
            if cb3.button("🌑", key=f"fsh_{i}", type=t("full_shade")):
                st.session_state.plants_df.at[i,"actual_sun"] = None if actual=="full_shade" else "full_shade"; st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — GARDEN GRID
# ══════════════════════════════════════════════════════════════════════════════
with tab_grid:
    st.markdown("# 📐 Garden Grid")
    if not PLANNER_AVAILABLE:
        st.warning("The Garden Grid requires `garden_planner_core.py`. See the **🗺️ Planning** tab for setup instructions.")
    elif st.session_state.planner_df is None:
        st.info("Generate a plan from the **🗺️ Planning** tab — the grid will load automatically.")
    else:
        plan_df = st.session_state.planner_df
        impact_level = ""
        if st.session_state.climate_projection:
            proj = st.session_state.climate_projection
            p = proj.get("projection") if isinstance(proj, dict) else proj
            if p: impact_level = getattr(p, "impact_level", "")
        try:
            from garden_planner_core import build_planner_html as _build_html
        except ImportError:
            _build_html = None
        if _build_html:
            try:
                planner_html = _build_html(plan_df, st.session_state.garden_name, impact_level)
                components.html(planner_html, height=950, scrolling=True)
                st.divider()
                st.download_button("📥 Download garden grid (HTML)", planner_html,
                                   file_name=f"{st.session_state.garden_name.replace(' ','_')}_grid.html",
                                   mime="text/html")
            except Exception as e:
                st.warning(f"Grid could not be rendered: {e}")
                st.dataframe(plan_df.head(20), use_container_width=True)
        else:
            st.info("Grid will be available once `build_planner_html` is exported from `garden_planner_core`.")
            st.dataframe(plan_df.head(20), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — CLIMATE
# ══════════════════════════════════════════════════════════════════════════════
with tab_climate:
    st.markdown("# 🌍 Climate Analysis")
    if not PLANNER_AVAILABLE:
        st.warning("Climate analysis requires `climate_projection.py`.")
    elif st.session_state.climate_projection is None:
        st.info("Generate a plan from the **🗺️ Planning** tab — climate data will load automatically.")
    else:
        proj = st.session_state.climate_projection
        p    = proj.get("projection") if isinstance(proj, dict) else proj
        if p:
            impact = getattr(p, "impact_level", "moderate")
            impact_color = {"low":"#2e7d32","moderate":"#e65100","high":"#b71c1c"}.get(impact,"#555")
            st.markdown(f"""<div class="climate-info">
              <strong>Climate impact level:</strong>
              <span style="color:{impact_color};font-weight:700;font-size:1.1rem">
                {impact.upper()}
              </span>
            </div>""", unsafe_allow_html=True)
            for attr in ["temperature_change","rainfall_change","growing_season_change","zone_shift","recommendations"]:
                val = getattr(p, attr, None)
                if val: st.markdown(f"**{attr.replace('_',' ').title()}:** {val}")
        st.markdown('<div class="sec-hdr">Current climate</div>', unsafe_allow_html=True)
        st.markdown(f"**Description:** {st.session_state.climate_desc}")
        if wx.get("ok"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Min temp (7 days)", f"{min(wx['mins'])}°C")
            c2.metric("Max temp (7 days)", f"{max(wx['maxs'])}°C")
            c3.metric("Rainfall (7 days)", f"{wx['weekly_rain']:.0f} mm")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════
with tab_template:
    st.markdown("# ⬇️ CSV Template")
    st.caption("Download the template, fill in your plants, and upload it via the sidebar.")
    st.divider()
    st.markdown("**Required columns:** `name`, `sun_needed`")
    st.markdown("**Optional:** `latin`, `actual_sun`, `soil`, `is_bulb`, `notes`")
    st.caption("If `pruning`, `feeding`, and `watering` are missing they are auto-filled from the built-in care database.")

    tpl = pd.DataFrame([
        {"name":"Lavender","latin":"Lavandula angustifolia","sun_needed":"full_sun","actual_sun":"","soil":"well_drained","is_bulb":"no","notes":""},
        {"name":"Hosta","latin":"Hosta spp.","sun_needed":"partial_shade","actual_sun":"","soil":"moist","is_bulb":"no","notes":""},
        {"name":"Dahlia","latin":"Dahlia spp.","sun_needed":"full_sun","actual_sun":"","soil":"well_drained","is_bulb":"yes","notes":""},
        {"name":"Mint","latin":"Mentha spp.","sun_needed":"partial_shade","actual_sun":"","soil":"moist","is_bulb":"no","notes":""},
        {"name":"Rose","latin":"Rosa spp.","sun_needed":"full_sun","actual_sun":"","soil":"rich","is_bulb":"no","notes":""},
    ])
    st.dataframe(tpl, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download CSV template",
                       tpl.to_csv(index=False).encode(),
                       "gradinata_template.csv", "text/csv",
                       use_container_width=True)
    st.divider()
    st.markdown("""
### Sun values reference

| Value | Meaning |
|---|---|
| `full_sun` | ☀️ Full sun — 6+ hours of direct sunlight |
| `partial_shade` | ⛅ Partial shade — 3–6 hours |
| `full_shade` | 🌑 Full shade — under 3 hours |
    """)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center;color:#888;padding:1rem;font-size:0.85rem">
  🌿 <strong>Gradinata</strong> · Dantara Software EOOD ·
  Data: Open-Meteo, PFAF, IPCC
</div>
""", unsafe_allow_html=True)
