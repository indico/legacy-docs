# -*- coding: utf-8 -*-
##
## $Id: schedule.py,v 1.75 2009/06/19 14:51:33 pferreir Exp $
##
## This file is part of CDS Indico.
## Copyright (C) 2002, 2003, 2004, 2005, 2006, 2007 CERN.
##
## CDS Indico is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 2 of the
## License, or (at your option) any later version.
##
## CDS Indico is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with CDS Indico; if not, write to the Free Software Foundation, Inc.,
## 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

"""
"""
import copy
from persistent import Persistent
from datetime import datetime,timedelta
from MaKaC.common.Counter import Counter
from MaKaC.errors import MaKaCError, TimingError, ParentTimingError,\
    EntryTimingError
from MaKaC.common import utils
from MaKaC.trashCan import TrashCanManager
from MaKaC.i18n import _
from pytz import timezone
from MaKaC.common.utils import daysBetween
from MaKaC.common.PickleJar import Retrieves
from MaKaC.common.PickleJar import DictPickler
from MaKaC.common.Conversion import Conversion
from MaKaC.common.contextManager import ContextManager

class Schedule:
    """base schedule class. Do NOT instantiate
    """

    def __init__( self, owner ):
        pass

    def getEntries( self ):
        return []

    def addEntry( self, entry, position=None ):
        return

    def removeEntry( self, entry ):
        return

    def getEntryPosition( self, entry ):
        return

    def moveEntry( self, entry, newPosition, after=1 ):
        return

    def getEntryLocator( self, entry ):
        return

    def getOwner( self ):
        return

    def reSchedule( self ):
        return

    def getEntryInPos( self, pos ):
        return None


class TimeSchedule(Schedule, Persistent):
    """
    """

    def __init__(self,owner):
        self._entries=[]
        self._owner=owner
        self._entryGen=Counter()
        self._v_allowReSchedule=True
        self._allowParallel=True

    def notifyModification(self):
        self.getOwner().notifyModification()

    @Retrieves(['MaKaC.schedule.TimeSchedule',
                'MaKaC.schedule.ConferenceSchedule'], 'entries', isPicklableObject=True)
    def getEntries( self ):
        return self._entries

    def hasEntriesBefore(self,d):
        """Tells wether there is any entry before the specified date
        """
        entries=self.getEntries()
        if len(entries)==0:
            return False
        return entries[0].getStartDate()<d

    def hasEntriesAfter(self,d):
        """Tells wether there is any entry after the specified date
        """
        entries=self.getEntries()
        if len(entries)==0:
            return False
        return self.calculateEndDate()>d

    def checkSanity( self ):
        if self.hasEntriesBefore(self.getStartDate()) or self.hasEntriesAfter(self.getEndDate()):
            raise TimingError("Sorry, cannot perform this date change: Some entries in the timetable would be outside the new dates [conference id => %s ]"%(self.getOwner().getConference().getId()))

    def isOutside(self,entry):
        """Tells whether an entry is outside the date boundaries of the schedule
        """
        ######################################
        # Fermi timezone awareness           #
        ######################################
        if entry.getStartDate() is not None:
            if entry.getStartDate()<self.getStartDate('UTC') or \
                    entry.getStartDate()>self.getEndDate('UTC'):
                return True
        if entry.getEndDate() is not None:
            if entry.getEndDate()<self.getStartDate('UTC') or \
                    entry.getEndDate()>self.getEndDate('UTC'):
                return True
        return False

    def hasEntry(self,entry):
        return entry.isScheduled() and entry.getSchedule()==self and\
            entry in self._entries

    def _addEntry(self,entry,check=2):
        """check parameter:
            0: no check at all
            1: check and raise error in case of problem
            2: check and adapt the owner dates"""

        if entry.isScheduled():
            # remove it from the old schedule and add it to this one
            entry.getSchedule().removeEntry(entry)

        owner = self.getOwner()
        tz = owner.getConference().getTimezone()

        # If user has entered start date use these dates
        # if the entry has not a pre-defined start date we try to find a place
        # within the schedule to allocate it
        if entry.getStartDate() is None:
            sDate=self.findFirstFreeSlot(entry.getDuration())
            if sDate is None:
                if check==2:
                    newEndDate = self.getEndDate() + entry.getDuration()

                    ContextManager.get('autoOps').append((owner,
                                                          "OWNER_END_DATE_EXTENDED",
                                                          owner,
                                                          newEndDate.astimezone(timezone(tz))))

                    owner.setEndDate(newEndDate, check)
                    sDate = self.findFirstFreeSlot(entry.getDuration())
                if sDate is None:
                    raise ParentTimingError( _("There is not enough time found to add this entry in the schedule (duration: %s)")%entry.getDuration(), _("Add Entry"))
            entry.setStartDate(sDate)
        #if the entry has a pre-defined start date we must make sure that it is
        #   not outside the boundaries of the schedule
        else:
            if entry.getStartDate() < self.getStartDate('UTC'):
                if check==1:
                    raise TimingError( _("Cannot schedule this entry because its start date (%s) is before its parents (%s)")%(entry.getStartDate(),self.getStartDate('UTC')),_("Add Entry"))
                elif check == 2:
                    ContextManager.get('autoOps').append((owner,
                                                          "OWNER_START_DATE_EXTENDED",
                                                          owner,
                                                          entry.getAdjustedStartDate(tz=tz)))
                    owner.setStartDate(entry.getStartDate(),check)
            elif entry.getEndDate()>self.getEndDate('UTC'):
                if check==1:
                    raise TimingError( _("Cannot schedule this entry because its end date (%s) is after its parents (%s)")%(entry.getEndDate(),self.getEndDate('UTC')),_("Add Entry"))
                elif check == 2:
                    ContextManager.get('autoOps').append((owner,
                                                          "OWNER_END_DATE_EXTENDED",
                                                          owner,
                                                          entry.getAdjustedEndDate(tz=tz)))
                    owner.setEndDate(entry.getEndDate(),check)
        #we make sure the entry end date does not go outside the schedule
        #   boundaries
        if entry.getEndDate() is not None and \
                (entry.getEndDate()<self.getStartDate('UTC') or \
                entry.getEndDate()>self.getEndDate('UTC')):
            raise TimingError( _("Cannot schedule this entry because its end date (%s) is after its parents (%s)")%(entry.getEndDate(),self.getEndDate()), _("Add Entry"))
        self._entries.append(entry)
        entry.setSchedule(self,self._getNewEntryId())
        self.reSchedule()
        self._p_changed = 1

    def _setEntryDuration(self,entry):
        if entry.getDuration() is None:
            entry.setDuration(0,5)

    def addEntry(self,entry):
        if (entry is None) or self.hasEntry(entry):
            return
        self._setEntryDuration(entry)
        result = self._addEntry(entry)
        self._p_changed = 1
        return result

    def _removeEntry(self,entry):
        self._entries.remove(entry)
        entry.setSchedule(None,"")
        entry.setStartDate(None)
        entry.delete()
        self._p_changed = 1

    def removeEntry(self,entry):
        if entry is None or not self.hasEntry(entry):
            return
        self._removeEntry(entry)

    def getEntryPosition( self, entry ):
        return self._entries.index( entry )

    def getOwner( self ):
        return self._owner

    ####################################
    # Fermi timezone awareness         #
    ####################################

    def getStartDate( self ,tz='UTC'):
        return self.getOwner().getAdjustedStartDate(tz)

    @Retrieves(['MaKaC.schedule.TimeSchedule',
                'MaKaC.schedule.ConferenceSchedule'], 'startDate', Conversion.datetime)
    def getAdjustedStartDate( self, tz=None ):
        return self.getOwner().getAdjustedStartDate(tz)

    def getEndDate( self, tz='UTC'):
        return self.getOwner().getAdjustedEndDate(tz)

    @Retrieves(['MaKaC.schedule.TimeSchedule',
                'MaKaC.schedule.ConferenceSchedule'], 'endDate', Conversion.datetime)
    def getAdjustedEndDate( self, tz=None):
        return self.getOwner().getAdjustedEndDate(tz)

    ####################################
    # Fermi timezone awareness(end)    #
    ####################################

    def cmpEntries(self,e1,e2):
        return cmp(e1.getStartDate(),e2.getStartDate())

    def reSchedule(self):
        try:
            if self._allowParalell:
                pass
        except AttributeError:
            self._allowParallel=True
        try:
            if self._v_allowReSchedule:
                pass
        except AttributeError:
            self._v_allowReSchedule=True
        if self._v_allowReSchedule:
            self._v_allowReSchedule=False
            self._entries.sort(self.cmpEntries)
            lastEntry=None
            for entry in self._entries:
                if lastEntry is not None:
                    if not self._allowParallel:
                        if lastEntry.collides(entry):
                            entry.setStartDate(lastEntry.getEndDate())
                lastEntry=entry
            self._v_allowReSchedule=True
        self._p_changed = 1

    def calculateEndDate( self ):
        if len(self._entries) == 0:
            return self.getStartDate()
        eDate = self.getStartDate()
        for entry in self._entries:
            if entry.getEndDate()>eDate:
                eDate = entry.getEndDate()
        return eDate

    def calculateStartDate( self ):
        if len(self._entries) == 0:
            return self.getStartDate()
        else:
            return self._entries[0].getStartDate()

    def getTimezone( self ):
        return self.getOwner().getConference().getTimezone()

    def getFirstFreeSlotOnDay(self,day):
        if not day.tzinfo:
            day = timezone(self.getTimezone()).localize(day)
        tz = day.tzinfo
        entries = self.getEntriesOnDay(day)
        if len(entries)==0:
            if self.getStartDate().astimezone(tz).date() == day.date():
                return self.getStartDate().astimezone(tz)
            return day.astimezone(timezone(self.getTimezone())).replace(hour=8,minute=0).astimezone(tz)
        else:
            return self.calculateDayEndDate(day)

    def calculateDayEndDate(self,day,hour=0,min=0):
        if day is None:
            return self.calculateEndDate()
        if not day.tzinfo:
            day = timezone(self.getTimezone()).localize(day)
        tz = day.tzinfo
        maxDate=day.replace(hour=hour,minute=min)
        entries = self.getEntriesOnDay(day)
        if hour != 0 or min != 0:
            return maxDate
        elif len(entries)==0:
            confstime = self.getOwner().getAdjustedStartDate()
            return day.astimezone(timezone(self.getTimezone())).replace(hour=confstime.hour,minute=confstime.minute).astimezone(tz)
        else:
            for entry in entries:
                if entry.getEndDate()>maxDate:
                    maxDate=entry.getEndDate().astimezone(tz)
            if maxDate.date() != day.date():
                maxDate = day.replace(hour=23,minute=59)
            return maxDate

    def calculateDayStartDate( self, day ):
        #
        # This determines where the times start on the time table.
        # day is a tz aware datetime
        if not day.tzinfo:
            day = timezone(self.getTimezone()).localize(day)
        tz = day.tzinfo
        entries = self.getEntriesOnDay(day)
        if len(entries) == 0:
            return timezone(self.getTimezone()).localize(datetime(day.year,day.month,day.day,8,0)).astimezone(tz)
        else:
            for entry in entries:
                if entry.getStartDate().astimezone(tz).date() >= day.date():
                    return entry.getStartDate().astimezone(tz)
                else:
                    return day.replace(hour=0,minute=0)

    def getEntryInPos( self, pos ):
        try:
            return self.getEntries()[int(pos)]
        except IndexError:
            return None

    def getEntriesOnDay( self, day ):
        """Returns a list containing all the entries which occur whithin the
            specified day. These entries will be ordered descending.
        """
        if not day.tzinfo:
            day = timezone(self.getTimezone()).localize(day)
        res = []
        for entry in self.getEntries():
            if entry.inDay( day ):
                res.append( entry )
        return res

    def getEntriesOnDate( self, date ):
        """Returns a list containing all the entries which occur whithin the
            specified day. These entries will be ordered descending.
        """
        res = []
        for entry in self.getEntries():
            if entry.onDate( date ):
                res.append( entry )
        return res

    def _getNewEntryId(self):
        try:
            if self._entryGen:
                pass
        except AttributeError:
            self._entryGen=Counter()
        return str(self._entryGen.newCount())

    def getEntryById(self,id):
        for entry in self.getEntries():
            if entry.getId()==str(id).strip():
                return entry
        return None

    def hasGap(self):
        """check if schedule has gap between two entries"""
        entries = self.getEntries()
        if len(entries) > 1:
            sDate = self.getStartDate('UTC')
            for entry in entries:
                if entry.getStartDate()!=sDate:
                    return True
                sDate = entry.getEndDate()
        return False

    def compact(self):
        """removes any overlaping among schedule entries and make them go one
            after the other without any gap
        """
        self._v_allowReSchedule=False
        refDate=self.getStartDate('UTC')
        for entry in self._entries:
            entry.setStartDate(refDate)
            refDate=entry.getEndDate()
        self._v_allowReSchedule=True

    def moveUpEntry(self,entry,tz=None):
        pass

    def moveDownEntry(self,entry,tz=None):
        pass

    def rescheduleTimes(self, type, diff, tz, day=None):
        pass

    def clear(self):
        while len(self._entries)>0:
            self._removeEntry(self._entries[0])
        self._p_changed = 1


    def findFirstFreeSlot(self,reqDur=None):
        """Tries to find the first free time slot available where an entry with
            the specified duration could be placed
        """
        d=self.getStartDate('UTC')
        for entry in self.getEntries():
            availDur=entry.getStartDate()-d
            if availDur!=0:
                if reqDur is not None and reqDur!=0:
                    if reqDur<=availDur:
                        return d
                else:
                    return d
            d=entry.getEndDate()
        availDur=self.getEndDate()-d
        if availDur!=0:
            if reqDur is not None and reqDur!=0:
                if reqDur<=availDur:
                    return d
            else:
                return d
        