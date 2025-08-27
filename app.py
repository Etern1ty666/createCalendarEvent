from fastapi import FastAPI, Request
import httpx, urllib.parse
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")
BITRIX_APP_AUTH_TOKEN = os.getenv("BITRIX_APP_AUTH_TOKEN")

TO_CALENDAR_OWNER_ID = 32
TARGET_ENTITY_TYPE_ID = 1086

TARGET_STAGES = [
    'DT1086_18:UC_1YZVCL',
    'DT1086_18:PREPARATION',
    'DT1086_18:CLIENT',
    'DT1086_18:UC_MCPPL0',
    'DT1086_18:UC_NRS39W',
    'DT1086_18:UC_D18ILJ',
    'DT1086_18:UC_R5BN3K',
    'DT1086_18:UC_68NYDF',
    'DT1086_18:UC_G1YOFJ',
    'DT1086_18:UC_MVFSN3',
    "DT1086_18:UC_VXW7ND",
    "DT1086_18:UC_H06UHP"
]
app = FastAPI()


async def event_already_exists(event_deal, event_from, event_to):
    # проверяем по ивентам в заданном промежутке и если в одном из ивентов есть совпадение на ID сделки, то считаем что ивент уже был создан на заданный промежуток
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BITRIX_WEBHOOK_URL}calendar.event.get",
            json = {
                "ownerId": TO_CALENDAR_OWNER_ID,
                "type": "user",
                "from": event_from,
                "to": event_to
            }
        )
        events = resp.json().get("result", [])
        print('Ивенты в данном промежутке:', events)
        for event in events:
            UF_CRM_CAL_EVENT = event.get("UF_CRM_CAL_EVENT") or []
            result = [s.removeprefix("D_") for s in UF_CRM_CAL_EVENT if s.startswith("D_")]
            if str(event_deal) in result:
                return {'status': True, 'event_id': event.get("ID")}
    return {'status': False, 'event_id': ''}


async def update_calendar_event_in_bitrix(event_id, start_date, end_date, title, deal_id, participants, object_passport_link, should_skip_time='Y'):
    params = {
                "id": int(event_id),
                "from": start_date,
                "to": end_date,
                "name": f"{title}",
                'crm_fields': [
                    f'D_{deal_id}'
                ],
                "type": "user",
                "ownerId": TO_CALENDAR_OWNER_ID,
                "section": 44,
                "is_meeting": "Y",
                "attendees": participants,
                "host": TO_CALENDAR_OWNER_ID,
                "remind": [{"type": "hour", "count": 1}, {"type": "day", "count": 1}],
                "accessibility": "busy",
                "description": f"Ссылка на паспорт объекта: {object_passport_link}\n\n *Создано автоматически*",
                "skip_time": should_skip_time
            }
    print('calendar.event.update with params:', params)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BITRIX_WEBHOOK_URL}calendar.event.update",
            json=params
        )
    return response



async def create_calendar_event_in_bitrix(start_date, end_date, title, deal_id, participants, object_passport_link, should_skip_time='Y'):
    params = {
                "from": start_date,
                "to": end_date,
                "name": f"{title}",
                'crm_fields': [
                    f'D_{deal_id}'
                ],
                "type": "user",
                "ownerId": TO_CALENDAR_OWNER_ID,
                "section": 44,
                "is_meeting": "Y",
                "attendees": participants,
                "host": TO_CALENDAR_OWNER_ID,
                "remind": [{"type": "hour", "count": 1}, {"type": "day", "count": 1}],
                "accessibility": "busy",
                "description": f"Ссылка на паспорт объекта: {object_passport_link}\n\n *Создано автоматически*",
                "skip_time": should_skip_time
            }
    print('calendar.event.add with params:', params)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BITRIX_WEBHOOK_URL}calendar.event.add",
            json=params
        )
    return response


@app.post("/createTO")
async def create_calendar_event(request: Request):
    body = (await request.body()).decode("utf-8")
    data = urllib.parse.parse_qs(body)
    print('Recieved data:', data)

    received_auth_token = data.get("auth[application_token]", [""])[0]
    if received_auth_token != BITRIX_APP_AUTH_TOKEN:
        print('Access denied')
        return {"status": "error", "message": "Access denied"}

    try:
        entity_type_id = int(data.get("data[FIELDS][ENTITY_TYPE_ID]", [""])[0])
    except Exception as e:
        print(f"ENTITY_TYPE_ID error: {e}")
        return {"status": "error", "message": f"ENTITY_TYPE_ID error: {e}"}
    if entity_type_id != TARGET_ENTITY_TYPE_ID:
        print('Unnecessary smart process')
        return {"status": "error", "message": "Unnecessary smart process"}

    item_id = data.get("data[FIELDS][ID]", [""])[0]
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BITRIX_WEBHOOK_URL}crm.item.get",
            json={"entityTypeId": entity_type_id, "id": item_id}
        )
        item = resp.json().get("result", {}).get("item", {})
        print('CRM item:', resp.json())

    current_stage = item.get("stageId") # jan feb mar etc...
    if current_stage not in TARGET_STAGES:
        print('Unnecessary stage')
        return {"status": "ok", "message": "Unnecessary stage"}

    engineer_users_id = item.get('ufCrm14_1730961599')
    second_engineer_id = item.get('ufCrm14_1749294833')
    start_date = item.get("ufCrm14_1749294949")
    end_date = item.get("ufCrm14_1750687377")
    object_passport_link = item.get("ufCrm14_1749298105853")
    deal_id = item.get("parentId2")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BITRIX_WEBHOOK_URL}crm.deal.get",
            json={"id": deal_id}
        )
        item = response.json().get("result", {})
        print('Привязанная сделка:', item)
    responsible_user_id = item.get('ASSIGNED_BY_ID')
    title = item.get("TITLE")

    participants = []
    for i in engineer_users_id:
        participants.append(i)
    participants.append(second_engineer_id)
    participants.append(responsible_user_id)

    fmt = "%Y-%m-%dT%H:%M:%S%z"

    start_dt = datetime.strptime(start_date, fmt)
    end_dt = datetime.strptime(end_date, fmt)

    if start_dt.hour == 0 and start_dt.minute == 0 and start_dt.second == 0:
        start_dt = start_dt.replace(hour=8, minute=0, second=0)
        print('new start date:', start_dt)

    if end_dt.date() == start_dt.date() and end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
        end_dt = end_dt.replace(hour=21, minute=0, second=0)
        print('new end date:', end_dt)

    start_date = start_dt.isoformat()
    end_date = end_dt.isoformat()

    result = await event_already_exists(event_deal=item.get('ID'), event_from=start_date ,event_to=end_date)
    if result['status'] == True:
        print('Edit event')
        response = await update_calendar_event_in_bitrix(event_id=result['event_id'], start_date=start_date, end_date=end_date, title=title,
                                                         deal_id=deal_id, participants=participants,
                                                         object_passport_link=object_passport_link)
        print('calendar.event.update response:', response.text)

        if response.status_code == 200:
            return {"status": "ok", "message": "Event updated"}
        else:
            return {"status": "error", "message": f'update error {response.text}'}


    response = await create_calendar_event_in_bitrix(start_date=start_date, end_date=end_date, title=title, deal_id=deal_id, participants=participants, object_passport_link=object_passport_link)
    print('calendar.event.add response:', response.text)
    if response.status_code == 200:
        return {"status": "ok", "message": "Event created"}
    else:
        return {"status": "error", "message": f'create error {response.text}'}


@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "Hi"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=os.getenv("HOST"), port=int(os.getenv("PORT", 8000)), reload=True)