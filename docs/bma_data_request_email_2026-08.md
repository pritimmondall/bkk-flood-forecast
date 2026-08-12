# BMA data request — August 2026

Four asks, ordered by measured value per unit of effort on BMA's side.

**This supersedes the priority ordering in `docs/data_requests.md`**, which was
written before the feature-ablation experiment (sets A–E, 2026-08-10). That
experiment replaced reasoning about which inputs *should* matter with
measurements of which ones *do*. Two things changed: rainfall moved decisively to
first place, and radar moved down — partly because BMA, not TMD, owns the Nong
Chok and Nong Khaem radars, which makes it the same conversation rather than a
separate one.

Everything below is stated as: what we ask for, what it is measured to change,
and what it costs to provide.

---

## The email

> **Subject:** Bangkok flood forecasting — results from your seven-year archive,
> and four requests
>
> Dear [name],
>
> We have finished the first full modelling pass on the drainage archive your
> department provided — seven years, 393 million sensor readings, 837 flood
> events at the 15 cm threshold. I want to report what it can do, what it cannot,
> and ask for four things that would change the second number.
>
> **What works.** Given the full archive, the model correctly identifies **53 out
> of every 100 flood events** in a year it has never seen. It does this from
> rainfall, canal levels and each road sensor's own recent history.
>
> **What does not.** Running on the data that is publicly available right now, the
> same model catches **5 in 100**. That is not a modelling problem and more
> engineering will not fix it. The model learned on your 131 rain gauges at
> five-minute intervals, and there is no public substitute — we tested the
> satellite products, the national weather API, and the commercial radar
> services, and each is either too coarse, too slow, or has no Bangkok stations.
>
> The four requests below close that gap. They are ordered smallest-first, and
> every number attached to them was measured, not estimated.
>
> **1. A read-only account on the pump portal** (`pumps.bangkok.go.th`). The map
> is public in a browser, but an automated client receives `403 Forbidden`. We
> notice the site already has a login, so an ordinary read-only account would
> resolve this without any change to your infrastructure — an API key or an
> allowlist entry would work equally well if you prefer. This also matters
> scientifically: when a pump station prevents a flood, our training data records
> it as "no flood" — indistinguishable from a street that was never at risk. Pump
> activity is the one signal that separates those two cases.
>
> **A related note rather than a request:** we were unable to reach
> `weather.bangkok.go.th` on 11 August 2026 — the connection is reset, including
> from a browser inside Bangkok. If that service has moved or been retired, we
> would be glad to know what replaced it.
>
> **2. A live feed from the rain gauge network** — the same 131 gauges whose
> history you have already shared. This is the single highest-value item: it
> takes live performance from 5 events in 100 to approximately **43**.
>
> **3. A live feed of canal water level and flow.** On its own it adds little;
> alongside rainfall it takes 43 to approximately **85**. It is a multiplier on
> rain, not a replacement for it.
>
> **4. Station coordinates** — latitude and longitude for the road flood sensors,
> rain gauges and canal stations, ideally with the water-level datum. This is one
> spreadsheet. Without it every station in a district shares one location, and
> the 1 m elevation model we built contributes **0.0%** to the forecast. It is
> the cheapest item on this list and the only one that is purely administrative.
>
> If it is useful, we would also welcome the **gridded output and archive** of
> BMA's Nong Chok and Nong Khaem radars — the images are already public; it is
> the underlying grid, and a historical archive to measure it against, that we
> would need.
>
> We are happy to work under whatever access conditions suit the department,
> including a fixed IP, rate limits, or a signed data agreement. A short technical
> annex is attached with the measurements behind each figure.
>
> With thanks for the archive — it is the reason there is anything to report.
>
> [name]
> [role, institution]

---

## Technical annex

### Where the numbers come from

Ablation on a single fixed split (train 2019–23, validate 2024, test 2025),
onset model, 15 cm threshold, 1-hour horizon, measuring **event probability of
detection** — the fraction of real flood events the system flags at all.

| Feature set available to the model | Events caught per 100 |
|---|---|
| A — everything, including road-sensor history | **53** |
| D — everything except road-sensor history | 45 |
| C — rain gauges + calendar + terrain | 23 |
| E — canal + forecast + calendar + terrain (public today) | **5** |
| B — weather forecast + calendar + terrain only | 2 |

Read C against E. Canal levels move the score from 2 to 5 without rainfall, and
from 23 to 45 with it. **Rainfall is the irreplaceable input**; canal level
sharpens a picture it cannot draw by itself.

Set D is worth noting separately: removing road-sensor history entirely still
leaves 45 in 100. The system does not depend on the sensors it is predicting for.

### Public substitutes, tested and ruled out

| Source | Why it does not work |
|---|---|
| GSMaP / JAXA | 0.1° ≈ 11 km — coarser than our existing district averages |
| GPM IMERG Early | Same resolution, ~4 h latency against a 1 h horizon |
| GFS via Open-Meteo | 13 km grid; Bangkok floods from cells 2–5 km across |
| TMD public API | 3-hourly, 2–3 Bangkok stations, registration required |
| ThaiWater | 11 Bangkok canal stations (useful, and we collect it) — **no rain stations** |
| ERA5 reanalysis | ~5-day publication lag |
| RainViewer | Past radar images only, personal-use licence |

### On coordinates, specifically

In the onset model, feature importance splits as: road-sensor history 86.8%,
rainfall 2.3%, canal 0.6%, **terrain 0.0%**.

Terrain scores zero not because elevation is irrelevant to flooding — it is the
mechanism — but because every station in a district is currently assigned that
district's centre point. All stations in a district therefore share identical
elevation, slope and depression-depth values, and no model can distinguish rows
whose inputs are identical. A separate check makes the same point from the other
direction: when any station in a district floods, only **35%** of its neighbours
do. The city varies at a scale finer than the one we can currently see.

### Honest statement of current limits

- **Median warning lead is 15 minutes** — one time step. This is a detection
  system, not yet a warning system. Lead time, not accuracy, is the next
  objective.
- **6.6 alert episodes per flood correctly warned.** Usable for an operations
  room, not for public notification, until it improves.
- Depth prediction intervals fail their coverage target and must not be shown as
  a p95. Severity is currently driven by which threshold was crossed.

### What we are already collecting, without asking

Since 2026-08-11, hourly: ThaiWater canal levels (11 Bangkok stations),
Open-Meteo forecast rain (50 district points), Traffy Fondue citizen flood
reports. None of these publish a downloadable past, so the history begins the day
collection begins. The pump portal is in the same category, which is why request
1 is time-sensitive in a way the others are not.

---

## Thai version

> **เรื่อง:** ผลการวิเคราะห์ข้อมูลย้อนหลัง 7 ปี และขอความอนุเคราะห์ข้อมูล 4 รายการ
>
> เรียน [ชื่อ]
>
> คณะผู้วิจัยได้ดำเนินการวิเคราะห์ข้อมูลจากคลังข้อมูลระบบระบายน้ำที่สำนักฯ
> ได้อนุเคราะห์ไว้เสร็จสิ้นแล้ว ประกอบด้วยข้อมูล 7 ปี จำนวน 393 ล้านรายการ
> และเหตุการณ์น้ำท่วมที่ระดับ 15 เซนติเมตร จำนวน 837 เหตุการณ์
> จึงขอรายงานผลและขอความอนุเคราะห์ข้อมูลเพิ่มเติม 4 รายการ ดังนี้
>
> **ผลที่ได้** เมื่อใช้ข้อมูลครบถ้วนจากคลังข้อมูลดังกล่าว แบบจำลองสามารถตรวจจับ
> เหตุการณ์น้ำท่วมได้ **53 จาก 100 เหตุการณ์** ในปีที่แบบจำลองไม่เคยเห็นข้อมูลมาก่อน
>
> **ข้อจำกัด** หากใช้เฉพาะข้อมูลที่เปิดเผยต่อสาธารณะในปัจจุบัน แบบจำลองเดียวกันนี้
> ตรวจจับได้เพียง **5 จาก 100 เหตุการณ์** ปัญหานี้มิได้เกิดจากตัวแบบจำลอง
> แต่เกิดจากการขาดข้อมูลปริมาณฝนที่วัดจริง แบบจำลองเรียนรู้จากสถานีวัดน้ำฝน 131
> สถานีของสำนักฯ ที่รายงานทุก 5 นาที ซึ่งไม่มีแหล่งข้อมูลสาธารณะใดทดแทนได้
>
> **ข้อ 1 — บัญชีผู้ใช้แบบอ่านอย่างเดียวของระบบสถานีสูบน้ำ** (`pumps.bangkok.go.th`)
> ระบบเปิดให้เข้าถึงผ่านเบราว์เซอร์อยู่แล้ว แต่ปฏิเสธการเรียกใช้แบบอัตโนมัติ
> (403 Forbidden) เนื่องจากเว็บไซต์มีระบบเข้าสู่ระบบอยู่แล้ว
> การออกบัญชีผู้ใช้แบบอ่านอย่างเดียวจึงน่าจะสะดวกที่สุด
> โดยไม่ต้องปรับแก้ระบบใด ๆ หรือจะออก API key ก็ได้เช่นกัน
> ข้อมูลนี้มีความสำคัญเชิงวิชาการ เนื่องจากเมื่อสถานีสูบน้ำทำงานและป้องกันน้ำท่วมได้
> ข้อมูลฝึกสอนของเราจะบันทึกว่า "ไม่เกิดน้ำท่วม" ซึ่งแยกไม่ออกจากถนนที่ไม่มีความเสี่ยงเลย
>
> **ข้อ 2 — ข้อมูลปริมาณน้ำฝนแบบเรียลไทม์** จากสถานีเดียวกันทั้ง 131 สถานี
> รายการนี้มีมูลค่าสูงสุด โดยจะเพิ่มความสามารถจาก 5 เป็นประมาณ **43 จาก 100 เหตุการณ์**
>
> **ข้อ 3 — ข้อมูลระดับน้ำและอัตราการไหลในคลองแบบเรียลไทม์**
> เมื่อใช้ร่วมกับข้อมูลฝน จะเพิ่มจาก 43 เป็นประมาณ **85 จาก 100 เหตุการณ์**
>
> **ข้อ 4 — พิกัดที่ตั้งของสถานี** (ละติจูด/ลองจิจูด) พร้อมระดับอ้างอิงของการวัดระดับน้ำ
> เป็นเพียงไฟล์ตารางเดียว ปัจจุบันสถานีทุกแห่งในเขตเดียวกันถูกกำหนดพิกัดเป็นจุดศูนย์กลางเขต
> ทำให้แบบจำลองความสูงภูมิประเทศความละเอียด 1 เมตรที่จัดทำไว้ มีส่วนช่วยเพียง **0.0%**
>
> หากเป็นไปได้ ขอความอนุเคราะห์ **ข้อมูลเรดาร์แบบกริดพร้อมข้อมูลย้อนหลัง**
> จากเรดาร์หนองจอกและหนองแขมของ กทม. เพิ่มเติมด้วย
>
> **ข้อสังเกตเพิ่มเติม (มิใช่การขอข้อมูล):** เมื่อวันที่ 11 สิงหาคม 2569
> คณะผู้วิจัยไม่สามารถเข้าถึงเว็บไซต์ `weather.bangkok.go.th` ได้
> (การเชื่อมต่อถูกรีเซ็ต) แม้จะเชื่อมต่อจากภายในกรุงเทพมหานคร
> หากระบบดังกล่าวย้ายที่อยู่หรือยกเลิกการให้บริการแล้ว
> ขอทราบระบบที่ใช้ทดแทนด้วยจะเป็นพระคุณยิ่ง
>
> คณะผู้วิจัยยินดีปฏิบัติตามเงื่อนไขการเข้าถึงข้อมูลตามที่สำนักฯ กำหนด
> ทั้งการกำหนด IP อัตราการเรียกใช้ หรือการจัดทำข้อตกลงการใช้ข้อมูล
> พร้อมนี้ได้แนบเอกสารทางเทคนิคประกอบตัวเลขแต่ละรายการ
>
> ขอขอบพระคุณสำหรับคลังข้อมูลที่ได้อนุเคราะห์ไว้ ซึ่งเป็นที่มาของผลการศึกษาทั้งหมดนี้
>
> ขอแสดงความนับถือ
> [ชื่อ] [ตำแหน่ง หน่วยงาน]

**Before sending the Thai version, have a Thai colleague check the register.**
Formal correspondence to a Thai government department (หนังสือราชการ) follows
conventions — salutation, ministry-specific forms of address, reference numbering
— that this draft does not attempt. The content is right; the formality may need
adjusting to house style.
