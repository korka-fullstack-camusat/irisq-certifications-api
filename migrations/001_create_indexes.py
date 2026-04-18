async def up(db):
    await db["users"].create_index("email", unique=True)
    await db["forms"].create_index("title")
    await db["responses"].create_index("form_id")
    await db["responses"].create_index("email")
