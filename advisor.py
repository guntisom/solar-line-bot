import os
import re
import json
from anthropic import Anthropic
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

SYSTEM_PROMPT = """คุณคือผู้ช่วยแนะนำการติดตั้งโซลาร์เซลล์บนหลังคาบ้านสำหรับเจ้าของบ้านในประเทศไทย
ตอบเป็นภาษาไทยเสมอ ใช้ภาษาสุภาพและเป็นกันเอง ใช้ emoji ช่วยให้อ่านง่าย

เก็บข้อมูลต่อไปนี้ทีละคำถาม อย่าถามรวมกันทีเดียว:
1. จังหวัดที่อยู่อาศัย
2. ค่าไฟเฉลี่ยต่อเดือน (บาท)
3. ใช้ไฟมากช่วงไหน — กลางวัน กลางคืน หรือทั้งคู่
4. เครื่องใช้ไฟฟ้าหลัก — จำนวนแอร์, มีเครื่องทำน้ำอุ่นไฟฟ้า, มีรถ EV ชาร์จที่บ้านไหม
5. บ้านเป็นของตัวเองและมีโฉนดไหม

เมื่อได้ข้อมูลครบทุกข้อแล้ว ให้ตอบว่า [READY_TO_ANALYZE] แล้วตามด้วย JSON บรรทัดเดียว:
[READY_TO_ANALYZE]{"province":"...","monthly_bill":0,"usage_pattern":"daytime/nighttime/mixed","num_aircons":0,"has_ev":false,"has_water_heater":false,"owns_home":true}

ห้ามวิเคราะห์หรือแนะนำผลิตภัณฑ์ก่อนได้ข้อมูลครบ"""

conversations = {}


def chat(user_id: str, message: str) -> str:
    if user_id not in conversations:
        conversations[user_id] = []

    conversations[user_id].append({"role": "user", "content": message})

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=conversations[user_id],
    )
    reply = response.content[0].text
    conversations[user_id].append({"role": "assistant", "content": reply})

    if "[READY_TO_ANALYZE]" in reply:
        analysis = _analyze(reply)
        conversations[user_id].append({"role": "assistant", "content": analysis})
        # Strip the tag from what we send back
        clean = reply.split("[READY_TO_ANALYZE]")[0].strip()
        return (clean + "\n\n" + analysis).strip() if clean else analysis

    return reply


def _analyze(claude_reply: str) -> str:
    match = re.search(r'\[READY_TO_ANALYZE\](\{.*?\})', claude_reply.replace("\n", ""))
    if not match:
        return "ขออภัยครับ ไม่สามารถประมวลผลข้อมูลได้ กรุณาลองใหม่อีกครั้ง"

    try:
        data = json.loads(match.group(1))
    except Exception:
        return "ขออภัยครับ ไม่สามารถประมวลผลข้อมูลได้ กรุณาลองใหม่อีกครั้ง"

    province = data.get("province", "")
    monthly_bill = float(data.get("monthly_bill", 3000))
    usage_pattern = data.get("usage_pattern", "mixed")
    num_aircons = int(data.get("num_aircons", 1))
    has_ev = data.get("has_ev", False)
    has_water_heater = data.get("has_water_heater", False)
    owns_home = data.get("owns_home", True)

    # System sizing
    monthly_units = monthly_bill / 4.5          # avg THB/unit
    base_kw = round(monthly_units / (30 * 5), 1)  # 5 peak sun hours Thailand
    ac_kw = num_aircons * 0.5
    ev_kw = 1.5 if has_ev else 0
    recommended_kw = max(round(base_kw + ac_kw * 0.3 + ev_kw, 1), 3.0)

    # Battery
    needs_battery = usage_pattern in ("nighttime", "mixed") or has_ev
    battery_reason = ""
    if has_ev:
        battery_reason = "เพราะมีรถ EV ชาร์จกลางคืน"
    elif usage_pattern == "nighttime":
        battery_reason = "เพราะใช้ไฟหนักกลางคืน"
    elif usage_pattern == "mixed":
        battery_reason = "เพื่อเก็บพลังงานส่วนเกินช่วงกลางวันไว้ใช้ตอนเย็น"

    # Cost estimate
    panel_cost = recommended_kw * 35000
    battery_cost = 90000 if needs_battery else 0
    total_cost = panel_cost + battery_cost
    monthly_saving = monthly_bill * (0.8 if not needs_battery else 0.95)
    payback_years = round(total_cost / (monthly_saving * 12), 1)

    # Search current financing offers
    financing = tavily.search(
        query="สินเชื่อโซลาร์เซลล์ GHB ธอส GSB ออมสิน อัตราดอกเบี้ย 2025",
        search_depth="basic", max_results=3, days=365,
    )
    financing_snippets = "\n".join(r["content"][:300] for r in financing["results"])

    # Search installers in province
    installers = tavily.search(
        query=f"บริษัทติดตั้งโซลาร์เซลล์ {province} มาตรฐาน รับรอง 2025",
        search_depth="basic", max_results=3, days=365,
    )
    installer_snippets = "\n".join(r["content"][:300] for r in installers["results"])

    prompt = f"""สรุปคำแนะนำการติดตั้งโซลาร์เซลล์สำหรับลูกค้า ตอบเป็นภาษาไทย ใช้ emoji ช่วยให้อ่านง่าย

ข้อมูลลูกค้า:
- จังหวัด: {province}
- ค่าไฟ/เดือน: {monthly_bill:,.0f} บาท
- รูปแบบการใช้ไฟ: {usage_pattern}
- จำนวนแอร์: {num_aircons} เครื่อง | มีเครื่องทำน้ำอุ่นไฟฟ้า: {has_water_heater} | มีรถ EV: {has_ev}
- เป็นเจ้าของบ้าน: {owns_home}

ผลการคำนวณ:
- ขนาดระบบที่แนะนำ: {recommended_kw} kW
- ต้องการแบตเตอรี่: {"ใช่ " + battery_reason if needs_battery else "ไม่จำเป็น (ใช้ไฟกลางวันเป็นหลัก)"}
- ราคาประมาณ (แผง): {panel_cost:,.0f} บาท
- ราคาแบตเตอรี่: {battery_cost:,.0f} บาท (ถ้ามี)
- รวมทั้งหมด: {total_cost:,.0f} บาท
- ประหยัดได้/เดือน: {monthly_saving:,.0f} บาท
- คืนทุนใน: {payback_years} ปี

ข้อมูลสินเชื่อจากการค้นหา:
{financing_snippets}

ข้อมูลช่างติดตั้งในพื้นที่:
{installer_snippets}

กรุณาสรุปใน 6 หัวข้อนี้:
1. ✅ ความเป็นไปได้และขนาดระบบที่แนะนำ (พร้อมเหตุผล)
2. 🔋 แบตเตอรี่ — ต้องการหรือไม่ เพราะอะไร
3. 💰 ราคาและระยะเวลาคืนทุน
4. 🏦 ตัวเลือกสินเชื่อที่ดีที่สุด (GHB, GSB, บัตรเครดิต) พร้อมเงื่อนไขเท่าที่ทราบ
5. 🏛️ สิทธิลดหย่อนภาษี — ลดหย่อนภาษีเงินได้บุคคลธรรมดาได้สูงสุด 200,000 บาท ตามมาตรการรัฐ อธิบายวิธีใช้สิทธิ์
6. 🔧 ช่างติดตั้งแนะนำในพื้นที่ {province} พร้อมคำแนะนำการเลือกช่าง

{"⚠️ หมายเหตุ: ลูกค้าไม่ได้เป็นเจ้าของบ้าน ควรแนะนำตรวจสอบสัญญาเช่าก่อนตัดสินใจ" if not owns_home else ""}"""

    result = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return result.content[0].text
