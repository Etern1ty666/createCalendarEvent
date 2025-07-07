from fastapi import FastAPI, Request
import httpx, urllib.parse
import os
from dotenv import load_dotenv

load_dotenv()

BITRIX_APP_AUTH_TOKEN = os.getenv("BITRIX_APP_AUTH_TOKEN")
BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")
TARGET_STAGE = os.getenv("TARGET_STAGE")
TARGET_ENTITY_TYPE_ID = os.getenv("TARGET_ENTITY_TYPE_ID")
TARGET_CALENDAR_ID = os.getenv("TARGET_CALENDAR_ID")
USER_PARAM_CODE = os.getenv("USER_PARAM_CODE")
FROM_PARAM_CODE = os.getenv("FROM_PARAM_CODE")
TO_PARAM_CODE = os.getenv("TO_PARAM_CODE")


app = FastAPI()

async def create_calendar_event_in_bitrix(user_id, start_date, end_date, title):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BITRIX_WEBHOOK_URL}calendar.event.add",
            json = {
                "from": start_date,
                "to": end_date,
                "type": "user",
                "ownerId": user_id,
                "section": TARGET_CALENDAR_ID,
                "name": title,
            }
        )
        return response


@app.get("/createCalendarEvent")
async def create_calendar_event(request: Request):
    body = (await request.body()).decode("utf-8")
    data = urllib.parse.parse_qs(body)

    received_auth_token = data.get("auth[application_token]", [""])[0]
    if received_auth_token != BITRIX_APP_AUTH_TOKEN:
        return {"status": "error", "message": "Access denied"}

    item_id = data.get("data[FIELDS][ID]", [""])[0]
    entity_type_id = data.get("data[FIELDS][ENTITY_TYPE_ID]", [""])[0]

    if not item_id or not entity_type_id:
        return {"status": "error", "message": "No [item_id] or [entity_type_id]"}

    if str(entity_type_id) != str(TARGET_ENTITY_TYPE_ID):
        return {"status": "error", "message": "Wrong [entity_type_id]"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BITRIX_WEBHOOK_URL}crm.item.get",
            json={"entityTypeId": entity_type_id, "id": item_id}
        )
        item = resp.json().get("result", {}).get("item", {})

    current_stage = item.get("stageId")
    if current_stage != TARGET_STAGE:
        return {"status": "ok", "message": "Unnecessary stage"}

    user_id = item.get(USER_PARAM_CODE)
    start_date = item.get(FROM_PARAM_CODE)
    end_date = item.get(TO_PARAM_CODE)
    title = item.get("title")
    if not all([user_id, start_date, end_date, title]):
        return {"status": "error", "message": "Blank fields in CRM process [user_id] or [start_date] or [end_date] or [title]"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BITRIX_WEBHOOK_URL}calendar.event.get",
            json={
                "ownerId": user_id,
                "type": "user",
                "from": start_date,
                "to": end_date
            }
        )
        events = resp.json().get("result", [])
        if events:
            return {"status": "ok", "message": "Event already exists"}

    cal_resp = await create_calendar_event_in_bitrix(user_id, start_date, end_date, title)

    if cal_resp.status_code == 200:
        return {"status": "ok", "message": "Event created"}
    else:
        return {"status": "error", "message": cal_resp.text}


@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "Hi"}


if name == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=os.getenv("HOST"), port=int(os.getenv("PORT")), reload=True)