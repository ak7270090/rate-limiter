"""Load the Lua scripts shipped in ``ratelab/storage/lua`` and register them with Redis."""

from importlib import resources

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

from ratelab.constants import LUA_SCRIPT_DIRECTORY, LUA_SCRIPT_PACKAGE, LUA_SCRIPT_SUFFIX


def read_lua_sources() -> dict[str, str]:
    """Script name (file name without ``.lua``) -> source."""
    script_directory = resources.files(LUA_SCRIPT_PACKAGE).joinpath(LUA_SCRIPT_DIRECTORY)
    return {
        script_file.name.removesuffix(LUA_SCRIPT_SUFFIX): script_file.read_text(encoding="utf-8")
        for script_file in script_directory.iterdir()
        if script_file.name.endswith(LUA_SCRIPT_SUFFIX)
    }


def register_lua_scripts(redis: Redis) -> dict[str, AsyncScript]:
    """Register every script; calls use ``EVALSHA`` and reload the script on ``NOSCRIPT``."""
    return {name: redis.register_script(source) for name, source in read_lua_sources().items()}
