from fastapi import FastAPI
from routers import users, payments, compliance, exceptions

app = FastAPI(
    title="Payment Exception Resolution Mock API",
    description="Mock backend service for simulating upstream banking systems.",
    version="1.0.0"
)

app.include_router(users.router)
app.include_router(payments.router)
app.include_router(compliance.router)
app.include_router(exceptions.router)

@app.get("/")
async def root():
    return {"message": "Welcome to the Payment Exception Resolution Mock API. Visit /docs for Swagger UI."}
