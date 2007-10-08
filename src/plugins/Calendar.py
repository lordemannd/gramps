# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

__author__ = "Douglas Blank <dblank@cs.brynmawr.edu>"
__version__ = "$Revision$"

#------------------------------------------------------------------------
#
# python modules
#
#------------------------------------------------------------------------
from gettext import gettext as _
from xml.parsers import expat
import datetime
import time
import const
import os

#------------------------------------------------------------------------
#
# GRAMPS modules
#
#------------------------------------------------------------------------
import BaseDoc
from BasicUtils import name_displayer
from PluginUtils import register_report
from ReportBase import Report, ReportUtils, ReportOptions, \
     MenuOptions, NumberOption, BooleanOption, TextOption, EnumeratedListOption, \
     FilterListOption, \
     CATEGORY_DRAW, CATEGORY_TEXT, MODE_GUI, MODE_BKI, MODE_CLI
import GrampsLocale
import gen.lib
from Utils import probably_alive, ProgressMeter
from FontScale import string_trim, string_width
pt2cm = ReportUtils.pt2cm
cm2pt = ReportUtils.cm2pt

#------------------------------------------------------------------------
#
# Calendar
#
#------------------------------------------------------------------------
class Calendar(Report):
    """
    Creates the Calendar object that produces the report.
    """
    def __init__(self,database,person,options_class):
        Report.__init__(self,database,person,options_class)
        self.titletext = "\n".join(options_class.handler.options_dict['titletext'])
        self.year = options_class.handler.options_dict['year']
        self.country = options_class.handler.options_dict['country']
        self.anniversaries = options_class.handler.options_dict['anniversaries']
        self.start_dow = options_class.handler.options_dict['start_dow'][0]
        self.maiden_name = options_class.handler.options_dict['maiden_name']
        self.alive = options_class.handler.options_dict['alive']
        self.birthdays = options_class.handler.options_dict['birthdays']
        self.text1 = "\n".join(options_class.handler.options_dict['text1'])
        self.text2 = "\n".join(options_class.handler.options_dict['text2'])
        self.text3 = "\n".join(options_class.handler.options_dict['text3'])
        self.filter = options_class.handler.options_dict['filter']
        self.filter.person = person
        name = name_displayer.display_formal(person)
        self.title = _("Calendar for %s") % name

    def get_short_name(self, person, maiden_name = None):
        """ Returns person's name, unless maiden_name given, unless married_name listed. """
        # Get all of a person's names:
        primary_name = person.get_primary_name()
        married_name = None
        names = [primary_name] + person.get_alternate_names()
        for n in names:
            if int(n.get_type()) == gen.lib.NameType.MARRIED:
                married_name = n
        # Now, decide which to use:
        if maiden_name != None:
            if married_name != None:
                first_name, family_name = married_name.get_first_name(), married_name.get_surname()
                call_name = married_name.get_call_name()
            else:
                first_name, family_name = primary_name.get_first_name(), maiden_name
                call_name = primary_name.get_call_name()
        else:
            first_name, family_name = primary_name.get_first_name(), primary_name.get_surname()
            call_name = primary_name.get_call_name()
        # If they have a nickname use it
        if call_name != None and call_name.strip() != "":
            first_name = call_name.strip()
        else: # else just get the first name:
            first_name = first_name.strip()
            if " " in first_name:
                first_name, rest = first_name.split(" ", 1) # just one split max
        return ("%s %s" % (first_name, family_name)).strip()
        
    def draw_rectangle(self, style, sx, sy, ex, ey):
        """ This should be in BaseDoc """
        self.doc.draw_line(style, sx, sy, sx, ey)
        self.doc.draw_line(style, sx, sy, ex, sy)
        self.doc.draw_line(style, ex, sy, ex, ey)
        self.doc.draw_line(style, sx, ey, ex, ey)

### The rest of these all have to deal with calendar specific things

    def add_day_item(self, text, year, month, day):
        """ Adds an item to a day. """
        month_dict = self.calendar.get(month, {})
        day_list = month_dict.get(day, [])
        day_list.append(text)
        month_dict[day] = day_list
        self.calendar[month] = month_dict

    def get_holidays(self, year, country = "United States"):
        """ Looks in multiple places for holidays.xml files """
        locations = [const.PLUGINS_DIR,
                     os.path.join(const.HOME_DIR,"plugins")]
        holiday_file = 'holidays.xml'
        for dir in locations:
            holiday_full_path = os.path.join(dir, holiday_file)
            if os.path.exists(holiday_full_path):
                self.process_holiday_file(holiday_full_path, year, country)

    def process_holiday_file(self, filename, year, country):
        """ This will process a holiday file """
        parser = Xml2Obj()
        element = parser.Parse(filename) 
        calendar = Holidays(element, country)
        date = datetime.date(year, 1, 1)
        while date.year == year:
            holidays = calendar.check_date( date )
            for text in holidays:
                self.add_day_item(text, date.year, date.month, date.day)
            date = date.fromordinal( date.toordinal() + 1)

    def write_report(self):
        """ The short method that runs through each month and creates a page. """
        # initialize the dict to fill:
        self.progress = ProgressMeter(_('Calendar'))
        self.calendar = {}
        # get the information, first from holidays:
        country, country_name = self.country
        if country != 0: # Don't include holidays
            self.get_holidays(self.year, _countries[country]) # _country is currently global
        # get data from database:
        self.collect_data()
        # generate the report:
        self.progress.set_pass(_('Formating months...'), 12)
        for month in range(1, 13):
            self.progress.step()
            self.print_page(month)
        self.progress.close()

    def print_page(self, month):
        """
        This method actually writes the calendar page.
        """
        style_sheet = self.doc.get_style_sheet()
        ptitle = style_sheet.get_paragraph_style("CAL-Title")
        ptext = style_sheet.get_paragraph_style("CAL-Text")
        pdaynames = style_sheet.get_paragraph_style("CAL-Daynames")
        pnumbers = style_sheet.get_paragraph_style("CAL-Numbers")
        ptext1style = style_sheet.get_paragraph_style("CAL-Text1style")

        self.doc.start_page()
        width = self.doc.get_usable_width()
        height = self.doc.get_usable_height()
        header = 2.54 # one inch
        self.draw_rectangle("CAL-Border", 0, 0, width, height)
        self.doc.draw_box("CAL-Title", "", 0, 0, width, header)
        self.doc.draw_line("CAL-Border", 0, header, width, header)
        year = self.year
        title = "%s %d" % (GrampsLocale.long_months[month], year)
        font_height = pt2cm(ptitle.get_font().get_size())
        self.doc.center_text("CAL-Title", title, width/2, font_height * 0.25)
        cell_width = width / 7
        cell_height = (height - header)/ 6
        current_date = datetime.date(year, month, 1)
        spacing = pt2cm(1.25 * ptext.get_font().get_size()) # 158
        if current_date.isoweekday() != self.start_dow:
            # Go back to previous first day of week, and start from there
            current_ord = current_date.toordinal() - ( (current_date.isoweekday() + 7) - self.start_dow ) % 7
        else:
            current_ord = current_date.toordinal()
        for day_col in range(7):
            font_height = pt2cm(pdaynames.get_font().get_size())
            self.doc.center_text("CAL-Daynames", 
                                 GrampsLocale.long_days[(day_col+self.start_dow) % 7 + 1],
                                 day_col * cell_width + cell_width/2,
                                 header - font_height * 1.5)
        for week_row in range(6):
            something_this_week = 0
            for day_col in range(7):
                thisday = current_date.fromordinal(current_ord)
                if thisday.month == month:
                    something_this_week = 1
                    self.draw_rectangle("CAL-Border", day_col * cell_width,
                                        header + week_row * cell_height,
                                        (day_col + 1) * cell_width,
                                        header + (week_row + 1) * cell_height)
                    last_edge = (day_col + 1) * cell_width
                    self.doc.center_text("CAL-Numbers", str(thisday.day),
                                         day_col * cell_width + cell_width/2,
                                         header + week_row * cell_height)
                    list = self.calendar.get(month, {}).get(thisday.day, [])
                    position = 0.0 
                    for p in list:
                        lines = p.count("\n") + 1 # lines in the text
                        position += (lines  * spacing)
                        current = 0
                        for line in p.split("\n"):
                            # make sure text will fit:
                            numpos = pt2cm(pnumbers.get_font().get_size())
                            if position + (current * spacing) - 0.1 >= cell_height - numpos: # font daynums
                                continue
                            font = ptext.get_font()
                            line = string_trim(font, line, cm2pt(cell_width + 0.2))
                            self.doc.draw_text("CAL-Text", line, 
                                              day_col * cell_width + 0.1,
                                              header + (week_row + 1) * cell_height - position + (current * spacing) - 0.1)
                            current += 1
                current_ord += 1
        if not something_this_week:
            last_edge = 0
        font_height = pt2cm(1.5 * ptext1style.get_font().get_size())
        self.doc.center_text("CAL-Text1style", self.text1, last_edge + (width - last_edge)/2, height - font_height * 3) 
        self.doc.center_text("CAL-Text2style", self.text2, last_edge + (width - last_edge)/2, height - font_height * 2) 
        self.doc.center_text("CAL-Text3style", self.text3, last_edge + (width - last_edge)/2, height - font_height * 1) 
        self.doc.end_page()

    def collect_data(self):
        """
        This method runs through the data, and collects the relevant dates
        and text.
        """
        people = self.filter.apply(self.database,
                                   self.database.get_person_handles(sort_handles=False))
        self.progress.set_pass(_('Filtering data...'), len(people))
        for person_handle in people:
            self.progress.step()
            person = self.database.get_person_from_handle(person_handle)
            birth_ref = person.get_birth_ref()
            birth_date = None
            if birth_ref:
                birth_event = self.database.get_event_from_handle(birth_ref.ref)
                birth_date = birth_event.get_date_object()
            alive = probably_alive(person, self.database, self.year)
            if self.birthdays and birth_date != None and ((self.alive and alive) or not self.alive):
                year = birth_date.get_year()
                month = birth_date.get_month()
                day = birth_date.get_day()
                age = self.year - year
                # add some things to handle maiden name:
                father_lastname = None # husband, actually
                if self.maiden_name == 0: # get husband's last name:
                    if person.get_gender() == gen.lib.Person.FEMALE:
                        family_list = person.get_family_handle_list()
                        if len(family_list) > 0:
                            fhandle = family_list[0] # first is primary
                            fam = self.database.get_family_from_handle(fhandle)
                            father_handle = fam.get_father_handle()
                            mother_handle = fam.get_mother_handle()
                            if mother_handle == person_handle:
                                if father_handle:
                                    father = self.database.get_person_from_handle(father_handle)
                                    if father != None:
                                        father_lastname = father.get_primary_name().get_surname()
                short_name = self.get_short_name(person, father_lastname)
                self.add_day_item("%s, %d" % (short_name, age), year, month, day)                
            if self.anniversaries and ((self.alive and alive) or not self.alive):
                family_list = person.get_family_handle_list()
                for fhandle in family_list: 
                    fam = self.database.get_family_from_handle(fhandle)
                    father_handle = fam.get_father_handle()
                    mother_handle = fam.get_mother_handle()
                    if father_handle == person.get_handle():
                        spouse_handle = mother_handle
                    else:
                        continue # with next person if this was the marriage event
                    if spouse_handle:
                        spouse = self.database.get_person_from_handle(spouse_handle)
                        if spouse:
                            spouse_name = self.get_short_name(spouse)
                            short_name = self.get_short_name(person)
                            if self.alive:
                                if not probably_alive(spouse, self.database, self.year):
                                    continue
                            for event_ref in fam.get_event_ref_list():
                                event = self.database.get_event_from_handle(event_ref.ref)
                                event_obj = event.get_date_object()
                                year = event_obj.get_year()
                                month = event_obj.get_month()
                                day = event_obj.get_day()
                                years = self.year - year
                                text = _("%(spouse)s and\n %(person)s, %(nyears)d") % {
                                    'spouse' : spouse_name,
                                    'person' : short_name,
                                    'nyears' : years,
                                    }
                                self.add_day_item(text, year, month, day)

class CalendarReport(Calendar):
    """ The Calendar text report """
    def write_report(self):
        """ The short method that runs through each month and creates a page. """
        # initialize the dict to fill:
        self.progress = ProgressMeter(_('Birthday and Anniversary Report'))
        self.calendar = {}
        # get the information, first from holidays:
        country, country_name = self.country
        if country != 0:
            self.get_holidays(self.year, _countries[country]) # currently global
        # get data from database:
        self.collect_data()
        # generate the report:
        self.doc.start_paragraph('BIR-Title') 
        self.doc.write_text(str(self.titletext) + ": " + str(self.year))
        self.doc.end_paragraph()
        if self.text1.strip() != "":
            self.doc.start_paragraph('BIR-Text1style')
            self.doc.write_text(str(self.text1))
            self.doc.end_paragraph()
        if self.text2.strip() != "":
            self.doc.start_paragraph('BIR-Text2style')
            self.doc.write_text(str(self.text2))
            self.doc.end_paragraph()
        if self.text3.strip() != "":
            self.doc.start_paragraph('BIR-Text3style')
            self.doc.write_text(str(self.text3))
            self.doc.end_paragraph()
        self.progress.set_pass(_('Formating months...'), 12)
        for month in range(1, 13):
            self.progress.step()
            self.print_page(month)
        self.progress.close()

    def print_page(self, month):
        """ Prints a month as a page """
        year = self.year
        self.doc.start_paragraph('BIR-Monthstyle')
        self.doc.write_text("%s %d" % (GrampsLocale.long_months[month], year))
        self.doc.end_paragraph()
        current_date = datetime.date(year, month, 1)
        current_ord = current_date.toordinal()
        started_day = {}
        for i in range(31):
            thisday = current_date.fromordinal(current_ord)
            if thisday.month == month:
                list = self.calendar.get(month, {}).get(thisday.day, [])
                for p in list:
                    p = p.replace("\n", " ")
                    if thisday not in started_day:
                        self.doc.start_paragraph("BIR-Daystyle")
                        self.doc.write_text("%s %s" % (GrampsLocale.long_months[month], str(thisday.day)))
                        self.doc.end_paragraph()
                        started_day[thisday] = 1
                    self.doc.start_paragraph("BIR-Datastyle")
                    self.doc.write_text(p)
                    self.doc.end_paragraph()
            current_ord += 1

class CalendarOptions(MenuOptions):
    """ Calendar options for graphic calendar """
    
    def add_menu_options(self, menu):
        """ Adds the options for the graphical calendar """
        category_name = _("Text Options")

        titletext = TextOption(_("Title text"),
                               [_("Birthday and Anniversary Report")])
        titletext.set_help(_("Title of calendar"))
        menu.add_option(category_name,"titletext", titletext)

        text1 = TextOption(_("Text Area 1"), [_("My Calendar")]) 
        text1.set_help(_("First line of text at bottom of calendar"))
        menu.add_option(category_name,"text1", text1)

        text2 = TextOption(_("Text Area 2"), [_("Produced with GRAMPS")])
        text2.set_help(_("Second line of text at bottom of calendar"))
        menu.add_option(category_name,"text2", text2)

        text3 = TextOption(_("Text Area 3"), ["http://gramps-project.org/"],)
        text3.set_help(_("Third line of text at bottom of calendar"))
        menu.add_option(category_name,"text3", text3)

        year = NumberOption(_("Year of calendar"), time.localtime()[0], 1000, 3000)
        year.set_help(_("Year of calendar"))
        menu.add_option(category_name,"year", year)

        filter = FilterListOption(_("Filter"))
        filter.add_item("person")
        filter.set_help(_("Select filter to restrict people that appear on calendar"))
        menu.add_option(category_name,"filter", filter)

        country = EnumeratedListOption(_("Country for holidays"), (0,_("Don't include holidays")))
        count = 0
        for c in  _countries:
            country.add_item(count, c)
            count += 1
        country.set_help(_("Select the country to see associated holidays"))
        menu.add_option(category_name,"country", country)

        start_dow = EnumeratedListOption(_("First day of week"), GrampsLocale.long_days[1])
        for count in range(1,8):
            # conversion between gramps numbering (sun=1) and iso numbering (mon=1) of weekdays below
            start_dow.add_item((count+5) % 7 + 1, GrampsLocale.long_days[count]) 
        start_dow.set_help(_("Select the first day of the week for the calendar"))
        menu.add_option(category_name, "start_dow", start_dow) 

        maiden_name = EnumeratedListOption(_("Birthday surname"),
                                           ("maiden", _("Wives use their own surname")))
        maiden_name.add_item("regular", _("Wives use husband's surname"))
        maiden_name.add_item("maiden", _("Wives use their own surname"))
        maiden_name.set_help(_("Select married women's displayed surname"))
        menu.add_option(category_name,"maiden_name", maiden_name)

        alive = BooleanOption(_("Include only living people"), True)
        alive.set_help(_("Include only living people in the calendar"))
        menu.add_option(category_name,"alive", alive)

        birthdays = BooleanOption(_("Include birthdays"), True)
        birthdays.set_help(_("Include birthdays in the calendar"))
        menu.add_option(category_name,"birthdays", birthdays)

        anniversaries = BooleanOption(_("Include anniversaries"), True)
        anniversaries.set_help(_("Include anniversaries in the calendar"))
        menu.add_option(category_name,"anniversaries", anniversaries)

    def make_my_style(self, default_style, name, description,
                      size=9, font=BaseDoc.FONT_SERIF, justified ="left",
                      color=None, align=BaseDoc.PARA_ALIGN_CENTER,
                      shadow = None, italic=0, bold=0, borders=0, indent=None):
        """ Creates paragraph and graphic styles of the same name """
        # Paragraph:
        f = BaseDoc.FontStyle()
        f.set_size(size)
        f.set_type_face(font)
        f.set_italic(italic)
        f.set_bold(bold)
        p = BaseDoc.ParagraphStyle()
        p.set_font(f)
        p.set_alignment(align)
        p.set_description(description)
        p.set_top_border(borders)
        p.set_left_border(borders)
        p.set_bottom_border(borders)
        p.set_right_border(borders)
        if indent:
            p.set(first_indent=indent)
        if justified == "left":
            p.set_alignment(BaseDoc.PARA_ALIGN_LEFT)       
        elif justified == "right":
            p.set_alignment(BaseDoc.PARA_ALIGN_RIGHT)       
        elif justified == "center":
            p.set_alignment(BaseDoc.PARA_ALIGN_CENTER)       
        default_style.add_paragraph_style(name,p)
        # Graphics:
        g = BaseDoc.GraphicsStyle()
        g.set_paragraph_style(name)
        if shadow:
            g.set_shadow(*shadow)
        if color != None:
            g.set_fill_color(color)
        if not borders:
            g.set_line_width(0)
        default_style.add_draw_style(name,g)
        
    def make_default_style(self, default_style):
        """ Adds the styles used in this report """
        self.make_my_style(default_style, "CAL-Title",
                           _('Title text and background color'), 20,
                           bold=1, italic=1,
                           color=(0xEA,0xEA,0xEA))
        self.make_my_style(default_style, "CAL-Numbers",
                           _('Calendar day numbers'), 13,
                           bold=1)
        self.make_my_style(default_style, "CAL-Text",
                           _('Daily text display'), 9)
        self.make_my_style(default_style,"CAL-Daynames",
                           _('Days of the week text'), 12,
                           italic=1, bold=1,
                           color = (0xEA,0xEA,0xEA))
        self.make_my_style(default_style,"CAL-Text1style",
                           _('Text at bottom, line 1'), 12)
        self.make_my_style(default_style,"CAL-Text2style",
                           _('Text at bottom, line 2'), 12)
        self.make_my_style(default_style,"CAL-Text3style",
                           _('Text at bottom, line 3'), 9)
        self.make_my_style(default_style,"CAL-Border",
                           _('Borders'), borders=True)
        
class CalendarReportOptions(CalendarOptions):
    """ Options for the calendar (birthday and anniversary) report """
    def make_default_style(self, default_style):
        """ Adds the options for the textual report """
        self.make_my_style(default_style, "BIR-Title",
                           _('Title text style'), 14,
                           bold=1, justified="center")
        self.make_my_style(default_style, "BIR-Datastyle",
                           _('Data text display'), 12, indent=1.0)
        self.make_my_style(default_style,"BIR-Daystyle",
                           _('Day text style'), 12, indent=.5,
                           italic=1, bold=1)
        self.make_my_style(default_style,"BIR-Monthstyle",
                           _('Month text style'), 12, bold=1)
        self.make_my_style(default_style,"BIR-Text1style",
                           _('Text at bottom, line 1'), 12, justified="center")
        self.make_my_style(default_style,"BIR-Text2style",
                           _('Text at bottom, line 2'), 12, justified="center")
        self.make_my_style(default_style,"BIR-Text3style",
                           _('Text at bottom, line 3'), 12, justified="center")

class Element:
    """ A parsed XML element """
    def __init__(self,name,attributes):
        'Element constructor'
        # The element's tag name
        self.name = name
        # The element's attribute dictionary
        self.attributes = attributes
        # The element's cdata
        self.cdata = ''
        # The element's child element list (sequence)
        self.children = []
        
    def AddChild(self,element):
        'Add a reference to a child element'
        self.children.append(element)
        
    def getAttribute(self,key):
        'Get an attribute value'
        return self.attributes.get(key)
    
    def getData(self):
        'Get the cdata'
        return self.cdata
        
    def getElements(self,name=''):
        'Get a list of child elements'
        #If no tag name is specified, return the all children
        if not name:
            return self.children
        else:
            # else return only those children with a matching tag name
            elements = []
            for element in self.children:
                if element.name == name:
                    elements.append(element)
            return elements

    def toString(self, level=0):
        """ Converts item at level to a XML string """
        retval = " " * level
        retval += "<%s" % self.name
        for attribute in self.attributes:
            retval += " %s=\"%s\"" % (attribute, self.attributes[attribute])
        c = ""
        for child in self.children:
            c += child.toString(level+1)
        if c == "":
            retval += "/>\n"
        else:
            retval += ">\n" + c + ("</%s>\n" % self.name)
        return retval

class Xml2Obj:
    """ XML to Object """
    def __init__(self):
        self.root = None
        self.nodeStack = []
        
    def StartElement(self,name,attributes):
        'SAX start element even handler'
        # Instantiate an Element object
        element = Element(name.encode(),attributes)
        # Push element onto the stack and make it a child of parent
        if len(self.nodeStack) > 0:
            parent = self.nodeStack[-1]
            parent.AddChild(element)
        else:
            self.root = element
        self.nodeStack.append(element)
        
    def EndElement(self,name):
        'SAX end element event handler'
        self.nodeStack = self.nodeStack[:-1]

    def CharacterData(self,data):
        'SAX character data event handler'
        if data.strip():
            data = data.encode()
            element = self.nodeStack[-1]
            element.cdata += data
            return

    def Parse(self,filename):
        'Creat a SAX parser and parse filename '
        Parser = expat.ParserCreate()
        # SAX event handlers
        Parser.StartElementHandler = self.StartElement
        Parser.EndElementHandler = self.EndElement
        Parser.CharacterDataHandler = self.CharacterData
        # Parse the XML File
        ParserStatus = Parser.Parse(open(filename,'r').read(), 1)
        return self.root

class Holidays:
    """ Class used to read XML holidays to add to calendar. """
    def __init__(self, elements, country="US"):
        self.debug = 0
        self.elements = elements
        self.country = country
        self.dates = []
        self.initialize()
    def set_country(self, country):
        """ Set the contry of holidays to read """
        self.country = country
        self.dates = []
        self.initialize()        
    def initialize(self):
        """ Parse the holiday date XML items """
        for country_set in self.elements.children:
            if country_set.name == "country" and country_set.attributes["name"] == self.country:
                for date in country_set.children:
                    if date.name == "date":
                        data = {"value" : "",
                                "name" : "",
                                "offset": "",
                                "type": "",
                                "if": "",
                                } # defaults
                        for attr in date.attributes:
                            data[attr] = date.attributes[attr]
                        self.dates.append(data)
    def get_daynames(self, y, m, dayname):
        """ Get the items for a particular year/month and day of week """
        if self.debug: print "%s's in %d %d..." % (dayname, m, y) 
        retval = [0]
        dow = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].index(dayname)
        for d in range(1, 32):
            try:
                date = datetime.date(y, m, d)
            except ValueError:
                continue
            if date.weekday() == dow:
                retval.append( d )
        if self.debug: print "dow=", dow, "days=", retval
        return retval
    def check_date(self, date):
        """ Returns items that match rules """
        retval = []
        for rule in self.dates:
            if self.debug: print "Checking ", rule["name"], "..."
            offset = 0
            if rule["offset"] != "":
                if rule["offset"].isdigit():
                    offset = int(rule["offset"])
                elif rule["offset"][0] in ["-","+"] and rule["offset"][1:].isdigit():
                    offset = int(rule["offset"])
                else:
                    # must be a dayname
                    offset = rule["offset"]
            if rule["value"].count("/") == 3: # year/num/day/month, "3rd wednesday in april"
                y, num, dayname, mon = rule["value"].split("/")
                if y == "*":
                    y = date.year
                else:
                    y = int(y)
                if mon.isdigit():
                    m = int(mon)
                elif mon == "*":
                    m = date.month
                else:
                    m = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                         'jul', 'aug', 'sep', 'oct', 'nov', 'dec'].index(mon) + 1
                dates_of_dayname = self.get_daynames(y, m, dayname)
                if self.debug: print "num =", num
                d = dates_of_dayname[int(num)]
            elif rule["value"].count("/") == 2: # year/month/day
                y, m, d = rule["value"].split("/")
                if y == "*":
                    y = date.year
                else:
                    y = int(y)
                if m == "*":
                    m = date.month
                else:
                    m = int(m)
                if d == "*":
                    d = date.day
                else:
                    d = int(d)
            ndate = datetime.date(y, m, d)
            if self.debug: print ndate, offset, type(offset)
            if type(offset) == int:
                if offset != 0:
                    ndate = ndate.fromordinal(ndate.toordinal() + offset)
            elif type(offset) in [type(u''), str]:
                dir = 1
                if offset[0] == "-":
                    dir = -1
                    offset = offset[1:]
                if offset in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']:
                    # next tuesday you come to, including this one
                    dow = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].index(offset)
                    ord = ndate.toordinal()
                    while ndate.fromordinal(ord).weekday() != dow:
                        ord += dir
                    ndate = ndate.fromordinal(ord)
            if self.debug: print "ndate:", ndate, "date:", date
            if ndate == date:
                if rule["if"] != "":
                    if not eval(rule["if"]):
                        continue
                retval.append(rule["name"])
        return retval

def get_countries():
    """ Looks in multiple places for holidays.xml files """
    locations = [const.PLUGINS_DIR,
                 os.path.join(const.HOME_DIR,"plugins")]
    holiday_file = 'holidays.xml'
    country_list = []
    for dir in locations:
        holiday_full_path = os.path.join(dir, holiday_file)
        if os.path.exists(holiday_full_path):
            cs = process_holiday_file(holiday_full_path)
            for c in cs:
                if c not in country_list:
                    country_list.append(c)
    country_list.sort()
    country_list.insert(0, _("Don't include holidays"))
    return country_list

def process_holiday_file(filename):
    """ This will process a holiday file for country names """
    parser = Xml2Obj()
    element = parser.Parse(filename)
    country_list = []
    for country_set in element.children:
        if country_set.name == "country":
            if country_set.attributes["name"] not in country_list:
                country_list.append(country_set.attributes["name"])
    return country_list

## Currently reads the XML file on load. Could move this someplace else
## so it only loads when needed.

_countries = get_countries()

#------------------------------------------------------------------------
#
# Register the plugins
#
#------------------------------------------------------------------------
register_report(
    name = 'calendar',
    category = CATEGORY_DRAW,
    report_class = Calendar,
    options_class = CalendarOptions,
    modes = MODE_GUI | MODE_BKI | MODE_CLI,
    translated_name = _("Calendar"),
    status = _("Stable"),
    author_name = "Douglas S. Blank",
    author_email = "dblank@cs.brynmawr.edu",
    description = _("Produces a graphical calendar"),
    )

register_report(
    name = 'birthday_report',
    category = CATEGORY_TEXT,
    report_class = CalendarReport,
    options_class = CalendarReportOptions,
    modes = MODE_GUI | MODE_BKI | MODE_CLI,
    translated_name = _("Birthday and Anniversary Report"),
    status = _("Stable"),
    author_name = "Douglas S. Blank",
    author_email = "dblank@cs.brynmawr.edu",
    description = _("Produces a report of birthdays and anniversaries"),
    )
