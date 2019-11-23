"""Services for the HEOS integration."""
import functools
import logging

from pyheos import CommandFailedError, Heos, HeosError, const
import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import HomeAssistantType

from .const import (
    ATTR_PASSWORD,
    ATTR_USERNAME,
    ATTR_GROUPMEMBERS,
    ATTR_MASTER,
#    ATTR_MASTER_UNJOIN,
    ATTR_ENTITY_ID,
    DOMAIN,
    SERVICE_GROUPINFO,
    SERVICE_JOIN,
    SERVICE_UNJOIN,    
    SERVICE_SIGN_IN,
    SERVICE_SIGN_OUT,
)

_LOGGER = logging.getLogger(__name__)

HEOS_SIGN_IN_SCHEMA = vol.Schema(
    {vol.Required(ATTR_USERNAME): cv.string, vol.Required(ATTR_PASSWORD): cv.string}
)

HEOS_SIGN_OUT_SCHEMA = vol.Schema({})

HEOS_GROUPINFO_SCHEMA = vol.Schema({})

HEOS_JOIN_SCHEMA = vol.Schema(
    {vol.Required(ATTR_MASTER): cv.entity_id, vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids}
)

HEOS_UNJOIN_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids}
)




def register(hass: HomeAssistantType, controller: Heos):
    """Register HEOS services."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SIGN_IN,
        functools.partial(_sign_in_handler, controller),
        schema=HEOS_SIGN_IN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SIGN_OUT,
        functools.partial(_sign_out_handler, controller),
        schema=HEOS_SIGN_OUT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GROUPINFO,
        functools.partial(_groupinfo_handler, controller),
        schema=HEOS_GROUPINFO_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_JOIN,
        functools.partial(_join_handler, controller),
        schema=HEOS_JOIN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNJOIN,
        functools.partial(_unjoin_handler, controller),
        schema=HEOS_UNJOIN_SCHEMA,
    )


def remove(hass: HomeAssistantType):
    """Unregister HEOS services."""
    hass.services.async_remove(DOMAIN, SERVICE_SIGN_IN)
    hass.services.async_remove(DOMAIN, SERVICE_SIGN_OUT)
    hass.services.async_remove(DOMAIN, SERVICE_GROUPINFO)
    hass.services.async_remove(DOMAIN, SERVICE_JOIN)    
    hass.services.async_remove(DOMAIN, SERVICE_UNJOIN)

async def _sign_in_handler(controller, service):
    """Sign in to the HEOS account."""
    if controller.connection_state != const.STATE_CONNECTED:
        _LOGGER.error("Unable to sign in because HEOS is not connected")
        return
    username = service.data[ATTR_USERNAME]
    password = service.data[ATTR_PASSWORD]
    try:
        await controller.sign_in(username, password)
    except CommandFailedError as err:
        _LOGGER.error("Sign in failed: %s", err)
    except HeosError as err:
        _LOGGER.error("Unable to sign in: %s", err)


async def _sign_out_handler(controller, service):
    """Sign out of the HEOS account."""
    if controller.connection_state != const.STATE_CONNECTED:
        _LOGGER.error("Unable to sign out because HEOS is not connected")
        return
    try:
        await controller.sign_out()
    except HeosError as err:
        _LOGGER.error("Unable to sign out: %s", err)

async def _groupinfo_handler(controller, service):
    """Group Info HEOS players."""
    if controller.connection_state != const.STATE_CONNECTED:
        _LOGGER.error("Unable to get info because HEOS is not connected")
        return
    entities = controller.players.values()
    groups = await controller.get_groups(refresh=True)
    groupstring = ""
    grouplist = []

    try:
        for group in groups.values():
            groupstring += "name: " +group.name.lower()
            groupstring += "members: " +group.leader.name.lower()
            for alreadymember in group.members:
                groupstring += "," +str(alreadymember.name.lower())
            #groupstring = current_members.rstrip(',')            
            grouplist.append(groupstring)
        _LOGGER.info("HEOS Groups are: %s", grouplist)
        return grouplist

    except HeosError as err:
        _LOGGER.error("Unable to get group info: %s", err)

async def _join_handler(controller, service):
    """Join HEOS players."""
    if controller.connection_state != const.STATE_CONNECTED:
        _LOGGER.error("Unable to join because HEOS is not connected")
        return
    master = service.data[ATTR_MASTER]
    entity_ids = service.data[ATTR_ENTITY_ID]
    entities = controller.players.values()
    groups = await controller.get_groups(refresh=True)
    current_master = ""
    current_members = ""
    groupstring = ""

    try:
        for group in groups.values():
            if group.leader.name.lower() in master:
                current_master = group.leader.name.lower()
                for alreadymember in group.members:
                    current_members += str(alreadymember.name.lower()) +","
                current_members = current_members.rstrip(',')            

        for player in entities:
            if player.name.lower() in master.lower():
                groupstring = str(player.player_id) +"," +groupstring   #adds master first
            elif any(player.name.lower() in e for e in entity_ids) and player.name.lower() in current_members:
                #Do nothing, if player mentioned in member and already is a member it means remove member => do not add to string
                groupstring +=""
            elif any(player.name.lower() in e for e in entity_ids) or player.name.lower() in current_members:
                #If player mentioned in member or already member (but not both, ref above) then add to string
                groupstring += str(player.player_id) +","
        groupstring = groupstring.rstrip(',')            

        await controller.create_group(groupstring,'')

    except HeosError as err:
        _LOGGER.error("Unable to join: %s", err)

async def _unjoin_handler(controller, service):
    """Unjoin HEOS players."""
    if controller.connection_state != const.STATE_CONNECTED:
        _LOGGER.error("Unable to unjoin because HEOS is not connected")
        return

    entity_ids = service.data[ATTR_ENTITY_ID]    
    groups = await controller.get_groups(refresh=True)

    try:
        for group in groups.values():
            if entity_ids != "[]" and group.leader.name.lower() in entity_ids:
                #Ungroup specific if specified
                await controller.create_group(str(group.leader.player_id),'')
            else:
                #Ungroup all if not specified                
                await controller.create_group(str(group.leader.player_id),'')
    except HeosError as err:
        _LOGGER.error("Unable to unjoin: %s", err)