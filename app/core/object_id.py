from bson import ObjectId
from fastapi import HTTPException, status


def parse_object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid ObjectId")
    return ObjectId(value)


def object_id_to_str(value: ObjectId | str | None) -> str | None:
    if value is None:
        return None
    return str(value)
