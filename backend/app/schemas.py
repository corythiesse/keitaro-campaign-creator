from datetime import datetime

import pycountry
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_core import PydanticCustomError


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # Must fit ``campaign_creation_logs.geo`` (VARCHAR(255)).
    geo: str = Field(min_length=2, max_length=255)
    offer_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise PydanticCustomError("invalid_name", "Название кампании обязательно")
        return value

    @field_validator("geo")
    @classmethod
    def normalize_geo(cls, value: str) -> str:
        # Commas are the UI separator; whitespace is accepted too.
        codes = [x.strip().upper() for x in value.replace(";", ",").replace(" ", ",").split(",") if x.strip()]
        if not codes:
            raise PydanticCustomError("invalid_geo", "Укажите хотя бы одну страну")
        invalid = sorted({code for code in codes if len(code) != 2 or pycountry.countries.get(alpha_2=code) is None})
        if invalid:
            raise PydanticCustomError(
                "invalid_geo",
                "Некорректные ISO-коды стран: {codes}",
                {"codes": ", ".join(invalid)},
            )
        unique = list(dict.fromkeys(codes))
        normalized = ", ".join(unique)
        if len(normalized) > 255:
            raise PydanticCustomError(
                "invalid_geo",
                "Слишком много стран: нормализованный список превышает 255 символов",
            )
        return normalized


class OfferOut(BaseModel):
    id: int
    keitaro_id: int
    keitaro_offer_stream_id: int | None = None
    campaign_id: int
    stream_id: int
    keitaro_stream_id: int | None = None
    name: str | None = None
    state: str | None = None
    share: int | None = None
    is_deleted: bool = False
    is_pinned: bool = False
    pinned_share: int | None = None
    origin: str = "keitaro"
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class StreamOut(BaseModel):
    id: int
    keitaro_id: int
    campaign_id: int
    name: str
    type: str | None = None
    schema: str | None = None
    position: int | None = None
    state: str | None = None
    action_type: str | None = None
    action_payload: str | None = None
    comments: str | None = None
    weight: float | None = None
    is_deleted: bool = False
    origin: str = "keitaro"
    offers: list[OfferOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)



class CampaignOut(BaseModel):
    id: int
    keitaro_id: int
    name: str
    alias: str | None = None
    state: str | None = None
    type: str | None = None
    domain_id: int | None = None
    group_id: str | None = None
    traffic_source_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class CampaignDetailOut(CampaignOut):
    streams: list[StreamOut] = Field(default_factory=list)


class CampaignEditorOut(CampaignDetailOut):
    keitaro_campaign_url: str | None = None
    has_local_changes: bool = False
    last_loaded_at: datetime | None = None
    last_pushed_at: datetime | None = None
    last_sync_error: str | None = None
    revision: int = 0
    warnings: list[str] = Field(default_factory=list)


class SyncLoadRequest(BaseModel):
    force: bool = False


class SyncPushRequest(BaseModel):
    expected_revision: int | None = None
    force: bool = False


class AddOfferRequest(BaseModel):
    offer_id: int = Field(gt=0)
    name: str | None = Field(default=None, max_length=255)
    expected_revision: int | None = None


class OfferPatch(BaseModel):
    is_deleted: bool | None = None
    is_pinned: bool | None = None
    pinned_share: int | None = None
    state: str | None = Field(default=None, max_length=20)
    expected_revision: int | None = None


class StreamSyncResult(BaseModel):
    stream_id: int | None = None
    keitaro_id: int | None = None
    status: str
    action: str | None = None
    code: str | None = None
    message: str | None = None


class SyncPushOut(BaseModel):
    success: bool
    code: str | None = None
    message: str | None = None
    campaign: CampaignEditorOut
    results: list[StreamSyncResult] = Field(default_factory=list)


class CreatedCampaignOut(BaseModel):
    id: int | None = None
    name: str | None = None
    alias: str | None = None


class CreatedStreamOut(BaseModel):
    id: int | None = None
    name: str


class CampaignCreatedOut(BaseModel):
    success: bool
    campaign: CreatedCampaignOut
    streams: list[CreatedStreamOut]


class HealthOut(BaseModel):
    ok: bool


class OfferSearchOut(BaseModel):
    id: int
    name: str


class CampaignHistoryOut(BaseModel):
    id: int
    campaign_name: str
    geo: str
    offer_id: int
    keitaro_campaign_id: int | None = None
    google_stream_id: int | None = None
    offer_stream_id: int | None = None
    status: str
    error_message: str | None = None
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)
