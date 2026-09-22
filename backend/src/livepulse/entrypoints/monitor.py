"""Monitor TikTok: una task por account_id con reconexion propia."""
import asyncio


async def monitor_account(account_id: str):
    # TODO: conectar proveedor real, guardar offset durable, emitir eventos con event_id.
    while True:
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break


async def main(accounts: list[str] = ["medical", "medical-2"]):
    await asyncio.gather(*(monitor_account(a) for a in accounts))


if __name__ == "__main__":
    asyncio.run(main())
