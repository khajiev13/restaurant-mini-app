from pydantic import BaseModel, model_validator


class TableResolveRequest(BaseModel):
    entry: str | None = None
    code: str | None = None

    @model_validator(mode="after")
    def require_exactly_one_identifier(self):
        if (self.entry is None) == (self.code is None):
            raise ValueError("Provide exactly one table entry or code")
        return self


class TableContextResponse(BaseModel):
    table_title: str
    hall_title: str
    service_percent: float
    manual_code: str
    access_token: str


class TableManifestItem(BaseModel):
    table_title: str
    hall_title: str
    service_percent: float
    manual_code: str
    start_param: str
    deep_link: str
