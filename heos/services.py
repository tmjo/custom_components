"""Services for the HEOS integration."""
import functools
import logging

from pyheos import CommandFailedError, Heos, HeosError, const
import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import HomeAssistantType

from homeassistant.components.media_player.const import DOMAIN as MEDIA_PLAYER_DOMAIN

from .const import (
    ATTR_PASSWORD,
    ATTR_USERNAME,
    DOMAIN,
    ATTR_GROUPMEMBERS,
    ATTR_MASTER,
    ATTR_ENTITY_ID,
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
    {vol.Optional(ATTR_ENTITY_ID, default=None): cv.comp_entity_ids}
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
        functools.partial(_groupinfo_handler, controller, hass),
        schema=HEOS_GROUPINFO_SCHEMA,
    )   
    hass.services.async_register(
        DOMAIN,
        SERVICE_JOIN,
        functools.partial(_join_handler, controller, hass),
        schema=HEOS_JOIN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNJOIN,
        functools.partial(_unjoin_handler, controller, hass),
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

async def _groupinfo_handler(controller, hass, service):
    """Group Info HEOS players."""
    if controller.connection_state != const.STATE_CONNECTED:
        _LOGGER.error("Unable to get info because HEOS is not connected")
        return
    players = controller.get_players(refresh=True)
    groups = await controller.get_groups(refresh=True)
    groupstring = ""
    grouplist = []

    try:
        for group in groups.values():
            groupstring += "name: " +group.name.lower()
            groupstring += "members: " +group.leader.name.lower()
            for alreadymember in group.members:
                groupstring += "," +str(alreadymember.name.lower())
            grouplist.append(groupstring)
        _LOGGER.info("HEOS Groups are: %s", grouplist)
        return grouplist

    except HeosError as err:
        _LOGGER.error("Unable to get group info: %s", err)

async def _join_handler(controller, hass, service):
    """Join HEOS players."""
    if controller.connection_state != const.STATE_CONNECTED:
        _LOGGER.error("Unable to join because HEOS is not connected")
        return
    master = service.data[ATTR_MASTER]
    entity_ids = service.data[ATTR_ENTITY_ID]

    _LOGGER.info("HEOS - Available players: %s", controller.players)
    _LOGGER.debug("HEOS - Trying to group: " +str(master) +" with " + str(entity_ids))

    groups = await controller.get_groups(refresh=True)
    current_members = ""
    groupstring = ""
 
    #Get devices
    master_device = [device for device in hass.data[MEDIA_PLAYER_DOMAIN].entities
        if device.entity_id == master
    ]

    #Get devices
    join_devices = [device for device in hass.data[MEDIA_PLAYER_DOMAIN].entities
        if any(device.entity_id in e for e in entity_ids)
    ]

    try:
        #Add master and check for current group
        groupstring = str(master_device[0].player_id) +","
        for group in groups.values():
            if group.leader.player_id == master_device[0].player_id:
                for alreadymember in group.members:
                    current_members += str(alreadymember.player_id) +","
        groupstring += current_members
        _LOGGER.info("HEOS - found group with master: " +str(master_device[0].player_id) +" already members: " +str(current_members))

        #Adds members
        for player in join_devices:
            groupstring += str(player.player_id) +","

        groupstring = groupstring.rstrip(',')
        _LOGGER.debug("HEOS - sending to controller: " +groupstring)
        await controller.create_group(groupstring,'')

    except HeosError as err:
        _LOGGER.error("Unable to join: %s", err)

async def _unjoin_handler(controller, hass, service):
    """Unjoin HEOS players."""
    if controller.connection_state != const.STATE_CONNECTED:
        _LOGGER.error("Unable to unjoin because HEOS is not connected")
        return

    if ATTR_ENTITY_ID not in service.data:
        entity_ids = None
    else:    
        entity_ids = service.data[ATTR_ENTITY_ID]    
    
    groups = await controller.get_groups(refresh=True)

    _LOGGER.debug("HEOS - trying to ungroup: " + str(entity_ids))

    #Get devices
    join_devices = [device for device in hass.data[MEDIA_PLAYER_DOMAIN].entities
        if any(device.entity_id in e for e in entity_ids)
    ]

    try:
        #Check current groups and remove the entities to unjoin
        groupstring = ""
        for group in groups.values():
            groupstring = str(group.leader.player_id) +","
            for alreadymember in group.members:
                if entity_ids is not None and entity_ids != "[]" and not any(str(alreadymember.player_id) in str(e.player_id) for e in join_devices):
                    #Keep members
                    groupstring += str(alreadymember.player_id) +","
                    _LOGGER.debug("HEOS - keeping: " +str(alreadymember.player_id))
                else:
                    #Do nothing, i.e. remove - if empty remove all
                    groupstring += ""
                    _LOGGER.debug("HEOS - removing: " +str(alreadymember.player_id))
        groupstring = groupstring.rstrip(',')            
        _LOGGER.debug("HEOS - sending to controller: " +groupstring)
        await controller.create_group(groupstring,'')
    except HeosError as err:
        _LOGGER.error("Unable to unjoin: %s", err)