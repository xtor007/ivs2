import asyncio
import json
from typing import Set, Dict, List, Any
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Body, Depends
from sqlalchemy import (
    create_engine,
    MetaData,
    Column,
    Integer,
    String,
    Float,
    DateTime,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from sqlalchemy.sql import select
from datetime import datetime
from pydantic import BaseModel, field_validator
from config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
)

# FastAPI app setup
app = FastAPI()
# SQLAlchemy setup
DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL)
metadata = MetaData()
SessionLocal = Session(bind=engine)

Base = declarative_base()
class Table(Base):
    __tablename__ = "processed_agent_data"

    id = Column("id", Integer, primary_key=True, index=True)
    road_state = Column("road_state", String)
    user_id = Column("user_id", Integer)
    x = Column("x", Float)
    y = Column("y", Float)
    z = Column("z", Float)
    longitude = Column("longitude", Float)
    latitude = Column("latitude", Float)
    timestamp = Column("timestamp", DateTime)


# SQLAlchemy model
class ProcessedAgentDataInDB(BaseModel):
    def __init__(self, id, road_state, user_id, x, y, z, latitude, longitude, timestamp):
        super().__init__(id=id, road_state=road_state, user_id=user_id, x=x, y=y, z=z, latitude=latitude, longitude=longitude, timestamp=timestamp)
        self.id = id
        self.road_state = road_state
        self.user_id = user_id
        self.x = x
        self.y = y
        self.z = z
        self.latitude = latitude
        self.longitude = longitude
        self.timestamp = timestamp

    id: int
    road_state: str
    user_id: int
    x: float
    y: float
    z: float
    latitude: float
    longitude: float
    timestamp: datetime


# FastAPI models
class AccelerometerData(BaseModel):
    x: float
    y: float
    z: float


class GpsData(BaseModel):
    latitude: float
    longitude: float


class AgentData(BaseModel):
    user_id: int
    accelerometer: AccelerometerData
    gps: GpsData
    timestamp: datetime

    @classmethod
    @field_validator("timestamp", mode="before")
    def check_timestamp(cls, value):
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError(
                "Invalid timestamp format. Expected ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)."
            )


class ProcessedAgentData(BaseModel):
    road_state: str
    agent_data: AgentData


# WebSocket subscriptions
subscriptions: Dict[int, Set[WebSocket]] = {}


# FastAPI WebSocket endpoint
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await websocket.accept()
    if user_id not in subscriptions:
        subscriptions[user_id] = set()
    subscriptions[user_id].add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        subscriptions[user_id].remove(websocket)


# Function to send data to subscribed users
async def send_data_to_subscribers(user_id: int, data):
    if user_id in subscriptions:
        for websocket in subscriptions[user_id]:
            await websocket.send_json(json.dumps(data))


# FastAPI CRUDL endpoints


@app.post("/processed_agent_data/")
async def create_processed_agent_data(data: List[ProcessedAgentData]):
    tables = []
    for item in data:
        agent_data = item.agent_data
        accelerometer = agent_data.accelerometer
        gps = agent_data.gps
        timestamp = agent_data.timestamp

        newTable = Table()

        newTable.road_state = item.road_state
        newTable.user_id = agent_data.user_id
        newTable.x = accelerometer.x
        newTable.y = accelerometer.y
        newTable.z = accelerometer.z
        newTable.latitude = gps.latitude
        newTable.longitude = gps.longitude
        newTable.timestamp = timestamp

        tables.append(newTable)

    SessionLocal.add_all(tables)
    SessionLocal.commit()


@app.get(
    "/processed_agent_data/{processed_agent_data_id}",
    response_model=ProcessedAgentDataInDB,
)
def read_processed_agent_data(processed_agent_data_id: int):
    table = SessionLocal.query(Table).get(processed_agent_data_id)
    return ProcessedAgentDataInDB(table.id, table.road_state, table.user_id, table.x, table.y, table.z, table.latitude, table.longitude, table.timestamp)


@app.get("/processed_agent_data/", response_model=list[ProcessedAgentDataInDB])
def list_processed_agent_data():
    result = []
    data = SessionLocal.query(Table).all()
    for table in data:
        result.append(ProcessedAgentDataInDB(table.id, table.road_state, table.user_id, table.x, table.y, table.z, table.latitude, table.longitude, table.timestamp))
    return result


@app.put(
    "/processed_agent_data/{processed_agent_data_id}",
    response_model=ProcessedAgentDataInDB,
)
def update_processed_agent_data(processed_agent_data_id: int, data: ProcessedAgentData):
    table = SessionLocal.query(Table).get(processed_agent_data_id)

    table.road_state = data.road_state
    table.user_id = data.agent_data.user_id
    table.x = data.agent_data.accelerometer.x
    table.y = data.agent_data.accelerometer.y
    table.z = data.agent_data.accelerometer.z
    table.latitude = data.agent_data.gps.latitude
    table.longitude = data.agent_data.gps.longitude
    table.timestamp = data.agent_data.timestamp

    SessionLocal.commit()

    return ProcessedAgentDataInDB(table.id, table.road_state, table.user_id, table.x, table.y, table.z, table.latitude, table.longitude, table.timestamp)


@app.delete(
    "/processed_agent_data/{processed_agent_data_id}",
    response_model=ProcessedAgentDataInDB,
)
def delete_processed_agent_data(processed_agent_data_id: int):
    table = SessionLocal.query(Table).get(processed_agent_data_id)

    SessionLocal.query(Table).filter(Table.id == processed_agent_data_id).delete()
    SessionLocal.commit()

    return ProcessedAgentDataInDB(table.id, table.road_state, table.user_id, table.x, table.y, table.z, table.latitude, table.longitude, table.timestamp)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
