from dotenv import load_dotenv

load_dotenv()

import asyncio  # noqa: E402
from .cli import main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(main())
