#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
A Command Line Wrapper to allow easy use of pyicloud for
command line scripts, and related.
"""
from __future__ import print_function
from builtins import input
import argparse
import pickle
import sys

from click import confirm

from pyicloud.base import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException
from . import utils


DEVICE_ERROR = "Please use the --device switch to indicate which device to use."


def create_pickled_data(idevice, filename):
    """
    This helper will output the idevice to a pickled file named
    after the passed filename.

    This allows the data to be used without resorting to screen / pipe
    scrapping.
    """
    pickle_file = open(filename, "wb")
    pickle.dump(idevice.attrs, pickle_file, protocol=pickle.HIGHEST_PROTOCOL)
    pickle_file.close()


def main(args=None):
    """Main commandline entrypoint."""
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description="Find My iPhone CommandLine Tool")

    parser.add_argument(
        "--username",
        action="store",
        dest="username",
        default="",
        help="Apple ID to Use",
    )
    parser.add_argument(
        "--password",
        action="store",
        dest="password",
        default="",
        help=(
            "Apple ID Password to Use; if unspecified, password will be "
            "fetched from the system keyring."
        ),
    )
    parser.add_argument(
        "-n",
        "--non-interactive",
        action="store_false",
        dest="interactive",
        default=True,
        help="Disable interactive prompts.",
    )
    parser.add_argument(
        "--delete-from-keyring",
        action="store_true",
        dest="delete_from_keyring",
        default=False,
        help="Delete stored password in system keyring for this username.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list",
        default=False,
        help="Short Listings for Device(s) associated with account",
    )
    parser.add_argument(
        "--llist",
        action="store_true",
        dest="longlist",
        default=False,
        help="Detailed Listings for Device(s) associated with account",
    )
    parser.add_argument(
        "--locate",
        action="store_true",
        dest="locate",
        default=False,
        help="Retrieve Location for the iDevice (non-exclusive).",
    )

    # Restrict actions to a specific devices UID / DID
    parser.add_argument(
        "--device",
        action="store",
        dest="device_id",
        default=False,
        help="Only effect this device",
    )

    # Trigger Sound Alert
    parser.add_argument(
        "--sound",
        action="store_true",
        dest="sound",
        default=False,
        help="Play a sound on the device",
    )

    # Trigger Message w/Sound Alert
    parser.add_argument(
        "--message",
        action="store",
        dest="message",
        default=False,
        help="Optional Text Message to display with a sound",
    )

    # Trigger Message (without Sound) Alert
    parser.add_argument(
        "--silentmessage",
        action="store",
        dest="silentmessage",
        default=False,
        help="Optional Text Message to display with no sounds",
    )

    # Lost Mode
    parser.add_argument(
        "--lostmode",
        action="store_true",
        dest="lostmode",
        default=False,
        help="Enable Lost mode for the device",
    )
    parser.add_argument(
        "--lostphone",
        action="store",
        dest="lost_phone",
        default=False,
        help="Phone Number allowed to call when lost mode is enabled",
    )
    parser.add_argument(
        "--lostpassword",
        action="store",
        dest="lost_password",
        default=False,
        help="Forcibly active this passcode on the idevice",
    )
    parser.add_argument(
        "--lostmessage",
        action="store",
        dest="lost_message",
        default="",
        help="Forcibly display this message when activating lost mode.",
    )

    # Output device data to an pickle file
    parser.add_argument(
        "--outputfile",
        action="store_true",
        dest="output_to_file",
        default="",
        help="Save device data to a file in the current directory.",
    )

    command_line = parser.parse_args(args)

    username = command_line.username
    password = command_line.password

    if username and command_line.delete_from_keyring:
        utils.delete_password_in_keyring(username)

    failure_count = 0
    while True:
        # Which password we use is determined by your username, so we
        # do need to check for this first and separately.
        if not username:
            parser.error("No username supplied")

        if not password:
            password = utils.get_password(
                username, interactive=command_line.interactive
            )

        if not password:
            parser.error("No password supplied")

        try:
            api = PyiCloudService(username.strip(), password.strip())
            if (
                not utils.password_exists_in_keyring(username)
                and command_line.interactive
                and confirm("Save password in keyring?")
            ):
                utils.store_password_in_keyring(username, password)

            if api.requires_2sa:
                # fmt: off
                print(
                    "\nTwo-step authentication required.",
                    "\nYour trusted devices are:"
                )
                # fmt: on

                devices = api.trusted_devices
                for i, device in enumerate(devices):
                    print(
                        "    %s: %s"
                        % (
                            i,
                            device.get(
                                "deviceName", "SMS to %s" % device.get("phoneNumber")
                            ),
                        )
                    )

                print("\nWhich device would you like to use?")
                device = int(input("(number) --> "))
                device = devices[device]
                if not api.send_verification_code(device):
                    print("Failed to send verification code")
                    sys.exit(1)

                print("\nPlease enter validation code")
                code = input("(string) --> ")
                if not api.validate_verification_code(device, code):
                    print("Failed to verify verification code")
                    sys.exit(1)

                print("")
            break
        except PyiCloudFailedLoginException:
            # If they have a stored password; we just used it and
            # it did not work; let's delete it if there is one.
            if utils.password_exists_in_keyring(username):
                utils.delete_password_in_keyring(username)

            message = "Bad username or password for {username}".format(
                username=username,
            )
            password = None

            failure_count += 1
            if failure_count >= 3:
                raise RuntimeError(message)

            print(message, file=sys.stderr)

    fmi_service = api.find_my_iphone
    fmi_service.refresh_client()
    for device in fmi_service.devices.values():
        if (
            not command_line.device_id
            or command_line.device_id.strip().lower() == device.id.strip().lower()
        ):
            # List device(s)
            if command_line.locate:
                fmi_service.refresh_client()

            if command_line.output_to_file:
                create_pickled_data(
                    device, filename=(device.name.strip().lower() + ".fmip_snapshot")
                )

            if command_line.longlist:
                print("-" * 30)
                print(device.name)
                for attr, value in device.attrs.items():
                    print("%20s - %s" % (attr, value))
            elif command_line.list:
                print("-" * 30)
                print("Name          - %s" % device.name)
                print("Display Name  - %s" % device.deviceDisplayName)
                print("Location      - %s" % device.location)
                print("Battery Level - %s" % device.batteryLevel)
                print("Battery Status- %s" % device.batteryStatus)
                print("Device Class  - %s" % device.deviceClass)
                print("Device Model  - %s" % device.deviceModel)

            # Play a Sound on a device
            if command_line.sound:
                if command_line.device_id:
                    device.play_sound()
                else:
                    raise RuntimeError(
                        "\n\n\t\t%s %s\n\n"
                        % (
                            "Sounds can only be played on a singular device.",
                            DEVICE_ERROR,
                        )
                    )

            # Display a Message on the device
            if command_line.message:
                if command_line.device_id:
                    device.display_message(
                        subject="A Message", message=command_line.message, sounds=True
                    )
                else:
                    raise RuntimeError(
                        "%s %s"
                        % (
                            "Messages can only be played on a singular device.",
                            DEVICE_ERROR,
                        )
                    )

            # Display a Silent Message on the device
            if command_line.silentmessage:
                if command_line.device_id:
                    device.display_message(
                        subject="A Silent Message",
                        message=command_line.silentmessage,
                        sounds=False,
                    )
                else:
                    raise RuntimeError(
                        "%s %s"
                        % (
                            "Silent Messages can only be played "
                            "on a singular device.",
                            DEVICE_ERROR,
                        )
                    )

            # Enable Lost mode
            if command_line.lostmode:
                if command_line.device_id:
                    device.lost_device(
                        number=command_line.lost_phone.strip(),
                        text=command_line.lost_message.strip(),
                        newpasscode=command_line.lost_password.strip(),
                    )
                else:
                    raise RuntimeError(
                        "%s %s"
                        % (
                            "Lost Mode can only be activated on a singular device.",
                            DEVICE_ERROR,
                        )
                    )
    sys.exit(0)


if __name__ == "__main__":
    main()
