# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from __future__ import absolute_import

import uuid
import logging

from tank.platform.qt import QtCore, QtGui

gnomekeyring = False
try:
    import gnomekeyring
except ImportError:
    from . import keyring


from .ui import resources_rc
from .ui import login as login_ui


class LoginError(Exception):
    """ Generic login specific exceptions """
    pass

class Login(QtGui.QDialog):
    """
    Manage authenticating a Pix login

    """

    # Constants that control where the settings are saved
    SETTINGS_APPLICATION = "Shotgun Login Framework"
    SETTINGS_ORGANIZATION = "Shotgun Software"

    # Logging
    __logger = logging.getLogger( "tk-framework-login.login")

    ##########################################################################################
    # public methods

    @classmethod
    def get_site(cls):
        """ returns the default site """
        (site, login) = cls.__get_public_values()
        cls.__logger.debug("get_site = %s", site)
        return site

    @classmethod
    def get_login(cls, dialog_message=None, force_dialog=False):
        """
        Return the login dictionary for the currently authenticated user.

        This will check saved values to see if there is a valid login
        cached. If no valid cached login information is found, a login
        dialog is displayed.

        This method returns a HumanUser dict for the login if it succeeds and
        None if it fails.
        :param dialog_message: A message to display in the login dialog
        :param force_dialog: If True, pop up the dialog even if some valid credentials are retrieved
        """
        # first check in memory cache
        result = getattr(cls, "_%s__login" % cls.__name__, None)
        if result and not force_dialog:
            return result

        # next see if the saved values return a valid user
        result = cls.__check_saved_values()
        if result and not force_dialog:
            return cls.__login

        # saved values did not authenticate run the dialog
        result = cls.__run_dialog(dialog_message)
        if result:
            return cls.__login

        # failed
        return None

    @classmethod
    def get_connection(cls, dialog_message=None):
        """
        Return an authenticated connection.

        This will check saved values to see if there is a valid login cached. 
        If no valid cached login information is found, a login
        dialog is displayed.

        This method returns a connection if it succeeds and None if
        it fails.
        """
        # first check in memory cache
        result = getattr(cls, "_%s__connection" % cls.__name__, None)
        if result:
            return result

        # next see if the saved values return a valid user
        result = cls.__check_saved_values()
        if result:
            return cls.__connection

        # saved values did not authenticate run the dialog
        result = cls.__run_dialog(dialog_message)
        if result:
            return cls.__connection

        # failed
        return None

    @classmethod
    def logout(cls):
        """
        Log out of the current connection.

        This will clear any stored values and require a new login to retrieve
        any further login on connection information.
        """
        cls.__login = None
        cls.__connection = None
        cls.__clear_password()

    @classmethod
    def _site_connect(cls, site, login, password):
        """
        Authenticate the given values against the given site.

        Needs to be implemented in classes deriving from this one
        And should always return a valid authenticated connection or raise an Exception.
        """
        raise NotImplementedError

    @classmethod
    def set_extra_credentials(cls):
        """
        Store extra credentials settings needed for login
        
        Needs to be implemented ( if needed ) in classes deriving from this one
        """
        raise NotImplementedError

    ##########################################################################################
    # private class methods

    @classmethod
    def __run_dialog(cls, dialog_message):
        """ run the login dialog """
        dialog = cls()
        if dialog_message is not None:
            dialog.set_message(dialog_message)
        dialog.raise_()
        dialog.activateWindow()
        result = dialog.exec_()
        if result == dialog.Accepted:
            return True

        # dialog was canceled
        return False

    @classmethod
    def __check_saved_values(cls):
        """ return whether the saved values authenticate or not """
        (site, login, password) = cls.__get_saved_values()
        try:
            return cls.__check_values(site, login, password)
        except LoginError:
            return False

    @classmethod
    def __get_public_values(cls):
        """ return the values that are stored unencrypted """
        settings = QtCore.QSettings(cls.SETTINGS_ORGANIZATION, cls.SETTINGS_APPLICATION)

        settings.beginGroup("loginInfo")
        site = settings.value("site", None)
        login = settings.value("login", None)
        settings.endGroup()

        return (site, login)

    @classmethod
    def __get_saved_values(cls):
        """ return a tuple of all the stored values """
        # load up the values stored via qsettings
        (site, login) = cls.__get_public_values()

        # load up the values stored securely in the os specific keyring
        if login:
            password = keyring_get_password("%s.login" % KEYRING_ROOT, login)
        else:
            password = None

        return (site, login, password)

    @classmethod
    def __clear_password(cls):
        """ clear password value """
        # remove settings stored in the os specific keyring
        settings = QtCore.QSettings(cls.SETTINGS_ORGANIZATION, cls.SETTINGS_APPLICATION)
        settings.beginGroup("loginInfo")
        login = settings.value("login", None)
        settings.endGroup()
        keyring_delete_password("%s.login" % KEYRING_ROOT, login)

    @classmethod
    def __clear_saved_values(cls):
        """ clear any saved values """
        settings = QtCore.QSettings(cls.SETTINGS_ORGANIZATION, cls.SETTINGS_APPLICATION)

        # remove settings stored via QSettings
        settings.beginGroup("loginInfo")
        settings.remove("")
        settings.endGroup()

        cls.__clear_password()

    @classmethod
    def __save_values(cls, site, login, password):
        """ save the given values securely """

        # make sure the keyring supports encryption
        kr = keyring_get_keyring()
        if not kr.encrypted():
            raise LoginError("keyring does not support encryption")

        # save the settings via qsettings
        settings = QtCore.QSettings(cls.SETTINGS_ORGANIZATION, cls.SETTINGS_APPLICATION)
        settings.beginGroup("loginInfo")
        settings.setValue("site", site)
        settings.setValue("login", login)
        settings.endGroup()

        # save these settings securely in the os specific keyring
        keyring_set_password("%s.login" % KEYRING_ROOT, login, password)

    @classmethod
    def __check_values(cls, site, login, password):
        """
        Authenticate the given values in Shotgun.

        Will always return True or raise a LoginError.
        """
        # If either login or password is not set
        # don't even try to login with the credentials
        if login is None or password is None:
            raise LoginError("Empty credentials")

        # try to connect to the site
        try:
            result = cls._site_connect(site, login, password)
        except Exception, e:
            raise LoginError("Could not connect to server", str(e))

        # cache results
        cls.__login = result
        cls.__connection = result

        return True

    ##########################################################################################
    # instance methods

    def __init__(self, parent=None):
        QtGui.QDialog.__init__(self, parent)

        # set the dialog to not have window decorations and always stay on top
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)

        # setup the gui
        self.ui = login_ui.Ui_LoginDialog()
        self.ui.setupUi(self)
        self.load_settings()

        # default focus
        if self.ui.site.text():
            self.ui.login.setFocus()
            self.ui.login.selectAll()
        else:
            self.ui.site.setFocus()

        self.connect(self.ui.sign_in, QtCore.SIGNAL("clicked()"), self.ok_pressed)
        self.connect(self.ui.cancel, QtCore.SIGNAL("clicked()"), self.cancel_pressed)

    def set_message(self, message):
        """ Set the message in the dialog """
        self.ui.message.setText(message)

    def cancel_pressed(self):
        self.close()

    def ok_pressed(self):
        """
        validate the values, accepting if login is successful and display an error message if not.
        """
        # pull values from the gui
        site = self.ui.site.text()
        login = self.ui.login.text()
        password = self.ui.password.text()

        # if not protocol specified assume https
        if len(site.split("://")) == 1:
            site = "https://%s" % site
            self.ui.site.setText(site)
        try:
            # try and authenticate
            self.__check_values(site, login, password)
        except LoginError, e:
            # authentication did not succeed
            self.ui.message.setText("%s\n\n%s" % (e[0], e[1]))
            return

        # all good, save the settings if requested and return accepted
        try:
            self.ui.message.setText("")
            self.save_settings()
        except LoginError:
            # error saving the settings
            self.ui.message.setText(
                "Could not store login information safely.\n\n" +
                "Please uncheck \"Remember me\" to continue.")
            return

        # dialog is done
        self.accept()

    def load_settings(self):
        """ Load the saved values for the dialog """
        (site, login, password) = self.__get_saved_values()

        # populate the ui
        self.ui.site.setText(site or "")
        self.ui.login.setText(login or "")
        self.ui.password.setText(password or "")

    def save_settings(self):
        """ Save the values from the dialog """
        # pull values from the gui
        site = self.ui.site.text()
        login = self.ui.login.text()
        password = self.ui.password.text()

        self.__save_values(site, login, password)

################################################################################
# Shotgun Login Implementation

class ShotgunLogin(Login):

    SETTINGS_APPLICATION = "Shotgun Desktop"
    SETTINGS_ORGANIZATION = "Shotgun Software"

    # Logging
    __logger = logging.getLogger("tk-desktop.login")

    @classmethod
    def _site_connect(cls, site, login, password):
        """
        Authenticate the given values in Shotgun.

        Return a valid authenticated connection or raise an Exception
        """
        # package shotgun_api3 until toolkit upgrades to a version that
        # allows for user based logins
        from ..shotgun_api3 import Shotgun

        # try to connect to Shotgun
        try:
            # connect and force an exchange so the authentication is validated
            connection = Shotgun(site, login=login, password=password)
            connection.find_one("HumanUser", [])
        except Exception, e:
            raise LoginError("Could not connect to server", str(e))

        try:
            result = connection.authenticate_human_user(login, password)
            if result is None:
                raise LoginError("Could not log in to server", "Login not valid.")
            return result
        except Exception, e:
            raise LoginError("Could not log in to server", str(e))

################################################################################
# Gnome Keyring Implementation


def _gnomekeyring_get_password(kerying, login):
    item, _ = __gnomekeyring_get_item(login)
    if item is None:
        return None
    return item.get_secret()


def _gnomekeyring_set_password(keyring, login, password):
    __gnomekeyring_get_item(login, create=True)
    login_key = __gnomekeyring_key_for_login(login)
    gnomekeyring.item_create_sync(
        "Login", gnomekeyring.ITEM_GENERIC_SECRET,
        login_key, {}, password, True)


def _gnomekeyring_delete_password(keyring, login):
    _, item_id = __gnomekeyring_get_item(login)
    if item_id is not None:
        gnomekeyring.item_delete_sync("Login", item_id)


def _gnomekeyring_get_keyring():
    return GnomeKeyring()


# Fake class since gnome keyring is always encrypted
class GnomeKeyring(object):
    def encrypted(self):
        return True


def __gnomekeyring_get_keychain_password():
    password, ok = QtGui.QInputDialog.getText(
        None,
        "Keychain Password",
        "Enter a password to protect your login info:",
        QtGui.QLineEdit.Password
    )

    if ok:
        return password
    return None


def __gnomekeyring_key_for_login(login):
    return "%s@www.shotgunsoftware.com" % login


def __gnomekeyring_get_item(login, create=False):
    login_key = __gnomekeyring_key_for_login(login)

    try:
        item_keys = gnomekeyring.list_item_ids_sync("Login")
    except gnomekeyring.NoSuchKeyringError:
        if create:
            password = __gnomekeyring_get_keychain_password()
            if password is not None:
                gnomekeyring.create_sync("Login", password)
                item_keys = []
        return None, None

    for key in item_keys:
        item_info = gnomekeyring.item_get_info_sync("Login", key)
        if item_info.get_display_name() == login_key:
            return item_info, key

    if not create:
        return None, None

    item_key = gnomekeyring.item_create_sync(
        "Login",
        gnomekeyring.ITEM_GENERIC_SECRET,
        login_key,
        {},
        str(uuid.uuid4()),
        True
    )
    item = gnomekeyring.item_get_info_sync("Login", item_key)
    return item, item_key

if gnomekeyring and gnomekeyring.is_available():
    KEYRING_ROOT = "Login"
    keyring_get_password = _gnomekeyring_get_password
    keyring_set_password = _gnomekeyring_set_password
    keyring_delete_password = _gnomekeyring_delete_password
    keyring_get_keyring = _gnomekeyring_get_keyring
else:
    KEYRING_ROOT = "com.shotgunsoftware.desktop"
    keyring_get_password = keyring.get_password
    keyring_set_password = keyring.set_password
    keyring_delete_password = keyring.delete_password
    keyring_get_keyring = keyring.get_keyring
