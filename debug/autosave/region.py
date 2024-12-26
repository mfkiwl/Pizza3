#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__project__ = "Pizza3"
__author__ = "Olivier Vitrac, Han Chen"
__copyright__ = "Copyright 2023"
__credits__ = ["Olivier Vitrac","Han Chen"]
__license__ = "GPLv3"
__maintainer__ = "Olivier Vitrac"
__email__ = "olivier.vitrac@agroparistech.fr"
__version__ = "0.58"

"""
    REGION provide tools to define native geometries in Python for LAMMPS

    TODO LIST (updated 2023-01-22, completed 2023-02-06)

    Please add here a full help with examples

    Public features (i.e. to be used by the end-user)

    	Let R1, R2 being pizza.regions()
    	R = R1 + R2 concatenates two regions (objects of R2 are inherited in R1, higher precedence for R2)
    	R.do()   generate the objects (do() should work as in pizza.script)
    	R.script returns the script (script() should work as in pizza.script)

    	Let o1, o2 are objects of R
    	R.o1 = [] delete o1
    	R.union(o1,o2,name=...) creates an union of o1 and o2 (in the LAMMPS sense, see region manual)
    	R.intersect(o1,o2,name=...) creates an intersection of o1 and o2 (in the LAMMPS sense, see region manual)
    	R.eval(expr,name=)
    		expr any algebraic expression including +
    		o1+o2+...

    Private features (i.e. to be used inside the code)

    	Overloading operators +, +=, | for any coregeometry object
   	Note that coregeometry have four main SECTIONS (scripts)
       SECTIONS["variables"]
       SECTIONS["region"]
       SECTIONS["create"]
       SECTIONS["group"]
       SECTIONS["move"]
   		USER, VARIABLES are overdefined as attributes

	+, += merge regions (no piping)
	| pipe them

   Add other geometries: block, sphere, cylinder....


"""


# INRAE\Olivier Vitrac - rev. 2023-08-11
# contact: olivier.vitrac@agroparistech.fr, han.chen@inrae.fr

# Revision history
# 2023-01-04 code initialization
# 2023-01-10 early alpha version
# 2023-01-11 alpha version (many fixes), wrap and align all displays with textwrap.fill, textwrap.shorten
# 2023-01-12 implement methods of keyword(units/rotate/open)
# 2023-01-18 split a script into subscripts to be executed in pipescripts
# 2023-01-19 use of LammpsGeneric.do() and hasvariables flag to manage VARIABLES
# 2023-01-20 app PythonPath management for VScode, add comments region.ellipsoid()
# 2023-01-22 todo list added
# 2023-01-24 implementation (o1 = R.E1, o2 = R.E2): o1+o2+... and o1 | o2 | ...
# 2023-01-25 full implementation of eval(), set(), get(), __setattr__(), __getattr__(), iterators
# 2023-01-26 add an example with for and join
# 2023-01-27 add coregometry.__iadd__, region.pipescript, region.script, region.do()
# 2023-01-27 true alpha version, workable with https://andeplane.github.io/atomify/
# 2023-01-31 fix browser and temporary files on Linux
# 2023-02-06 major update, internal documentation for all objects, livelammps attribute
# 2023-02-16 fix object counters, add width, height, depth to region(), data are stored in live
# 2023-02-16 add a specific >> (__rshift__) method for LammpsVariables, to be used by pipescript.do()
# 2023-02-21 add gel compression exemple, modification of the footer section to account for several beadtypes
# 2023-03-16 add emulsion, collection
# 2023-07-07 fix region.union()
# 2023-07-15 add the preffix "$" to units, fix prism and other minor issues
# 2023-07-15 (code works with the current state of Workshop4)
# 2023-07-17 avoid duplicates if union or intersect is used, early implemeantion of "move"
# 2023-07-19 add region.hasfixmove, region.livelammps.options["static" | "dynamic"]
# 2023-07-19 early design for LammpsGroup class, Group class, region.group()
# 2023-07-20 reimplement, validate and extend the original emulsion example
# 2023-07-25 add group section (not active by default)
# 2023-07-29 symmetric design for coregeometry and collection objects with flag control, implementation in pipescript
# 2023-07-29 fix for the class LammpsCollectionGroup() - previous bug resolved
# 2023-08-11 full implementation of the space-filled model such as in pizza.raster

# %% Imports and private library
import os, sys
from datetime import datetime
from copy import copy as duplicate
from copy import deepcopy as deepduplicate
from textwrap import fill, shorten
from webbrowser import open as livelammps

# update python path if needed (for development only)
# try: pwd = os.path.abspath(os.path.join(os.path.dirname(__file__),".."))
# except NameError: pwd = os.getcwd()
# try: sys.path.index(pwd) # sys.path.insert(0, os.getcwd())
# except ValueError: sys.path.append(pwd)
# print('\n>>>',pwd,'\n')
# os.chdir(pwd)

# import struct, param, paramauto, span
from pizza.private.struct import *
from pizza.script import pipescript, script, scriptdata, span

# protected properties in region
protectedregionkeys = ('name', 'live', 'nbeads' 'volume', 'mass', 'radius', 'contactradius', 'velocities', \
                        'forces', 'filename', 'index', 'objects', 'nobjects', 'counter','_iter_',\
                        'livelammps','copy', 'hasfixmove', 'spacefilling', 'isspacefilled', 'spacefillingbeadtype'
                            )

# livelammps
#livelammpsURL = 'https://editor.lammps.org/'
livelammpsURL = "https://andeplane.github.io/atomify/"
livetemplate = {
    'mass':'mass		    %d 1.0',
    'pair_coeff':'pair_coeff	    %d %d 1.0 1.0 2.5',
    }
groupprefix = "GRP"  # prefix for all group IDs created from a named region
fixmoveprefix = "FM" # prefix for all fix move IDs created from a named region
# %% Low level functions
# wrap and indent text for variables
wrap = lambda k,op,v,indent,width,maxwidth: fill(
        shorten(v,width=maxwidth+indent,
        fix_sentence_endings=True),
        width=width+indent,
        initial_indent=" "*(indent-len(k)-len(op)-2)+f'{k} {op} ',
        subsequent_indent=' '*(indent+(1 if v[0]=='"' else 0) )
        )

# remove $ from variable names
cleanname = lambda name: "".join([x for x in name if x!="$"])

# %% Top generic classes for storing region data and objects
# they are not intended to be used outside script data and objects

class regiondata(paramauto):
    """
        class of script parameters
            Typical constructor:
                DEFINITIONS = regiondata(
                    var1 = value1,
                    var2 = value2
                    )
        See script, struct, param to get review all methods attached to it
    """
    _type = "RD"
    _fulltype = "region data"
    _ftype = "definition"

    def generatorforlammps(self,verbose=False,hasvariables=False):
        """
            generate LAMMPS code from regiondata (struct)
            generatorforlammps(verbose,hasvariables)
            hasvariables = False is used to prevent a call of generatorforLammps()
            for scripts others than LammpsGeneric ones
        """
        nk = len(self)
        if nk>0:
            self.sortdefinitions(raiseerror=False)
            s = self.tostruct()
            ik = 0
            fmt = "variable %s equal %s"
            cmd = "\n#"+"_"*40+"\n"+f"#[{str(datetime.now())}]\n" if verbose else ""
            cmd += f"\n# Definition of {nk} variables (URL: https://docs.lammps.org/variable.html)\n"
            if hasvariables:
                for k in s.keys():
                    ik += 1
                    end = "\n" if ik<nk else "\n"*2
                    v = getattr(s,k)
                    if v is None: v = "NULL"
                    if isinstance(v,(int,float)) or v == None:
                        cmd += fmt % (k,v)+end
                    elif isinstance(v,str):
                        cmd += fmt % (k,f'{v}')+end
                    elif isinstance(v,(list,tuple)):
                        cmd += fmt % (k,span(v))+end
                    else:
                        raise TypeError(f"unsupported type for the variable {k} set to {v}")
                if verbose: cmd += "#"+"_"*40+"\n"
        return cmd

class regioncollection(struct):
    """ regioncollection class container (not to be called directly) """
    _type = "collect"               # object type
    _fulltype = "Collections"    # full name
    _ftype = "collection"        # field name
    def __init__(self,*obj,**kwobj):
        # store the objects with their alias
        super().__init__(**kwobj)
        # store objects with their real names
        for o in obj:
            if isinstance(o,region):
                s = struct.dict2struct(o.objects)
                list_s = s.keys()
                for i in range(len(list_s)): self.setattr(list_s[i], s[i].copy())
            elif o!=None:
                self.setattr(o.name, o.copy())

# %% PRIVATE SUB-CLASSES
# Use the equivalent methods of raster() to call these constructors

class LammpsGeneric(script):
    """
        common class to override standard do() method from script
        LammpsVariables, LammpsRegion, LammpsCreate are LammpsGeneric
        note:: the only difference with the common script class is that
        LammpsGeneric accepts VARIABLES AND To SHOW THEM
    """
    def do(self,printflag=True,verbose=False):
        """ generate the LAMMPS code with VARIABLE definitions """
        if self.DEFINITIONS.hasvariables and hasattr(self,'VARIABLES'): # attribute VARIABLES checked 2023-08-11
            cmd = f"#[{str(datetime.now())}] {self.name} > {self.SECTIONS[0]}" \
                if verbose else ""
            if len(self.VARIABLES)>0: cmd += \
            self.VARIABLES.generatorforlammps(verbose=verbose,hasvariables=True)
        else:
            cmd = ""
        cmd += super().do(printflag=False)
        if printflag: print(cmd)
        return cmd

class LammpsVariables(LammpsGeneric):
    """
        script for LAMMPS variables section
        myvars = LammpsVariables(regiondata(var1=...),ID='....',style='....')
    """
    name = "LammpsVariables"
    SECTIONS = ["VARIABLES"]
    position = 2
    role = "variable command definition"
    description = "variable name style args"
    userid = "variable"
    version = 0.1
    verbose = True

    # Definitions used in TEMPLATE
    DEFINITIONS = scriptdata(
                    ID = "${ID}",
                 style = "${style}",
          hasvariables = True
                    )

    # Template  (using % instead of # enables replacements)
    TEMPLATE = "% variables to be used for ${ID} ${style}"

    def __init__(self,VARIABLES=regiondata(),**userdefinitions):
        """ constructor of LammpsVariables """
        super().__init__(**userdefinitions)
        self.VARIABLES = VARIABLES

    # override >>
    def __rshift__(self,s):
        """ overload right  shift operator (keep only the last template) """
        if isinstance(s,script):
            dup = deepduplicate(self) # instead of duplicate (added 2023-08-11)
            dup.DEFINITIONS = dup.DEFINITIONS + s.DEFINITIONS
            dup.USER = dup.USER + s.USER
            if self.DEFINITIONS.hasvariables and s.DEFINITIONS.hasvariables:
                dup.VARIABLES = s.VARIABLES
            dup.TEMPLATE = s.TEMPLATE
            return dup
        else:
            raise TypeError("the second operand must a script object")


class LammpsCreate(LammpsGeneric):
    """ script for LAMMPS variables section """
    name = "LammpsCreate"
    SECTIONS = ["create_atoms"]
    position = 4
    role = "create_atoms command"
    description = "create_atoms type style args keyword values ..."
    userid = "create"
    version = 0.1
    verbose = True

    # Definitions used in TEMPLATE
    DEFINITIONS = scriptdata(
                    ID = "${ID}",
                 style = "${style}",
                 hasvariables = False
                    )

    # Template (using % instead of # enables replacements)
    TEMPLATE = """
% Create atoms of type ${beadtype} for ${ID} ${style} (https://docs.lammps.org/create_atoms.html)
create_atoms ${beadtype} region ${ID}
"""

class LammpsSetGroup(LammpsGeneric):
    """ script for LAMMPS set group section """
    name = "LammpsSetGroup"
    SECTIONS = ["set group"]
    position = 4
    role = "create_atoms command"
    description = "set group groupID type beadtype"
    userid = "setgroup"
    version = 0.1
    verbose = True

    # Definitions used in TEMPLATE
    DEFINITIONS = scriptdata(
                    ID = "${ID}",
               groupID = "$"+groupprefix+"${ID}", # freeze the interpretation,
          hasvariables = False
                    )

    # Template (using % instead of # enables replacements)
    TEMPLATE = """
% Reassign atom type to ${beadtype} for the group ${groupID} associated with region ${ID} (https://docs.lammps.org/set.html)
set group ${groupID} type ${beadtype}
"""

class LammpsMove(LammpsGeneric):
    """ script for LAMMPS variables section """
    name = "LammpsMove"
    SECTIONS = ["move_fix"]
    position = 6
    role = "move along a trajectory"
    description = "fix ID group-ID move style args keyword values ..."
    userid = "move"
    version = 0.2
    verbose = True

    # Definitions used in TEMPLATE
    DEFINITIONS = scriptdata(
                    ID = "${ID}",
                moveID = "$"+fixmoveprefix+"${ID}", # freeze the interpretation
               groupID = "$"+groupprefix+"${ID}", # freeze the interpretation
                 style = "${style}",
                  args = "${args}",
          hasvariables = False
                    )

    # Template (using % instead of # enables replacements)
    TEMPLATE = """
# Move atoms fix ID group-ID move style args keyword values (https://docs.lammps.org/fix_move.html)
% move_fix for group ${groupID} using ${style}
% prefix "g" added to ${ID} to indicate a group of atoms
% prefix "fm" added to ${ID} to indicate the ID of the fix move
fix ${moveID} ${groupID} move ${style} ${args}
"""


class LammpsRegion(LammpsGeneric):
    """ generic region based on script """
    name = "LammpsRegion"
    SECTIONS = ["REGION"]
    position = 3
    role = "region command definition"
    description = "region ID style args keyword arg"
    userid = "region"              # user name
    version = 0.1                  # version
    verbose = True

    # DEFINITIONS USED IN TEMPLATE
    DEFINITIONS = scriptdata(
                    ID = "${ID}",
                 style = "${style}",
                  args = "${args}",
                  side = "${side}",
                 units = "${units}",
                  move = "${move}",
                rotate = "${rotate}",
                  open = "${open}",
          hasvariables = False
                    )

    # Template  (using % instead of # enables replacements)
    TEMPLATE = """
% Create region ${ID} ${style} args ...  (URL: https://docs.lammps.org/region.html)
# keywords: side, units, move, rotate, open
# values: in|out, lattice|box, v_x v_y v_z, v_theta Px Py Pz Rx Ry Rz, integer
region ${ID} ${style} ${args} ${side}${units}${move}${rotate}${open}
"""


class LammpsGroup(LammpsGeneric):
    """ generic group class based on script """
    name = "LammpsGroup"
    SECTIONS = ["GROUP"]
    position = 5
    role = "group command definition"
    description = "group ID region regionID"
    userid = "region"              # user name
    version = 0.2                  # version
    verbose = True

    # DEFINITIONS USED IN TEMPLATE
    DEFINITIONS = scriptdata(
                    ID = "${ID}",
               groupID = "$"+groupprefix+"${ID}", # freeze the interpretation
          countgroupID = "$count"+"${groupID}", # either using $
           grouptoshow = ["${groupID}"], # or []
                 hasvariables = False
                    )

    # Template  (using % instead of # enables replacements)
    TEMPLATE = """
% Create group ${groupID} region ${ID} (URL: https://docs.lammps.org/group.html)
group ${groupID} region ${ID}
variable ${countgroupID} equal count(${grouptoshow})
print "Number of atoms in ${groupID}: \${{countgroupID}}"
"""


class LammpsCollectionGroup(LammpsGeneric):
    """ Collection group class based on script """
    name = "LammpsCollection Group"
    SECTIONS = ["COLLECTIONGROUP"]
    position = 6
    role = "group command definition for a collection"
    description = "group ID union regionID1 regionID2..."
    userid = "collectionregion"              # user name
    version = 0.3                            # version
    verbose = True

    # DEFINITIONS USED IN TEMPLATE
    DEFINITIONS = scriptdata(
                    ID = "${ID}",
               groupID = "$"+groupprefix+"${ID}", # freeze the interpretation
          hasvariables = False
                    )

    # Template  (ID is spanned over all regionIDs)
    TEMPLATE = """
% Create group ${groupID} region ${ID} (URL: https://docs.lammps.org/group.html)
group ${groupID} union ${ID}
"""

class LammpsHeader(LammpsGeneric):
    """ generic header for pizza.region """
    name = "LammpsHeader"
    SECTIONS = ["HEADER"]
    position = 0
    role = "header for live view"
    description = "To be used with https://editor.lammps.org/"
    userid = "header"              # user name
    version = 0.1                  # version
    verbose = False

    # DEFINITIONS USED IN TEMPLATE
    DEFINITIONS = scriptdata(
                    width = 10,
                   height = 10,
                    depth = 10,
                    nbeads = 1,
            hasvariables = False
                    )

    # Template
    TEMPLATE = """
# --------------[    INIT   ]--------------
# assuming generic LJ units and style
units           lj
atom_style	    atomic
lattice		    fcc 0.8442
# ------------------------------------------

# --------------[    B O X   ]--------------
variable        halfwidth equal ${width}/2
variable        halfheight equal ${height}/2
variable        halfdepth equal ${depth}/2
region box block -${halfwidth} ${halfwidth} -${halfheight} ${halfheight} -${halfdepth} ${halfdepth}
create_box	${nbeads} box
# ------------------------------------------
"""

class LammpsSpacefilling(LammpsGeneric):
    """ Spacefilling script: fill space with a block """
    name = "LammpsSpacefilling"
    SECTIONS = ["SPACEFILLING"]
    position = 1
    role = "fill space with fillingbeadtype atoms"
    description = 'fill the whole space (region "filledspace") with default atoms (beadtype)'
    userid = "spacefilling"              # user name
    version = 0.1                        # version
    verbose = False

    # DEFINITIONS USED IN TEMPLATE
    DEFINITIONS = scriptdata(
             fillingunits = "${fillingunits}",
             fillingwidth = "${fillingwidth}",
            fillingheight = "${fillingheight}",
             fillingdepth = "${fillingdepth}",
               fillingxlo = "-${fillingwidth}/2",
               fillingxhi = "${fillingwidth}/2",
               fillingylo = "-${fillingheight}/2",
               fillingyhi = "${fillingheight}/2",
               fillingzlo = "-${fillingdepth}/2",
               fillingzhi = "${fillingdepth}/2",
          fillingbeadtype = "${fillingbeadtype}",
             fillingstyle = "${block}",
             hasvariables = False
                    )

    # Template
    TEMPLATE = """
region filledspace ${fillingstyle} ${fillingxlo} ${fillingxhi} ${fillingylo} ${fillingyhi} ${fillingzlo} ${fillingzhi}
create_atoms ${fillingbeadtype} region filledspace
# ------------------------------------------
"""

class LammpsFooter(LammpsGeneric):
    """ generic header for pizza.region """
    name = "LammpsFooter"
    SECTIONS = ["FOOTER"]
    position = 1000
    role = "footer for live view"
    description = "To be used with https://editor.lammps.org/"
    userid = "footer"              # user name
    version = 0.1                  # version
    verbose = False

    # DEFINITIONS USED IN TEMPLATE
    DEFINITIONS = scriptdata(
                      run = 1,
             hasvariables = False
                    )

    # Template
    TEMPLATE = """
# --------------[  DYNAMICS  ]--------------
${mass}
velocity	    all create 1.44 87287 loop geom
pair_style	    lj/cut 2.5
${pair_coeff}
neighbor	    0.3 bin
neigh_modify	delay 0 every 20 check no
fix		        1 all nve
run		        ${run}
# ------------------------------------------
"""

class coregeometry:
    """
        core geometry object
        (helper class for attributes, side,units, move, rotate, open)

        SECTIONS store scripts (variables, region and create for the geometry)
        USER = common USER definitions for the three scripts
        VARIABLES = variables definitions (used by variables only)
        update() propagate USER to the three scripts
        script returns SECTIONS as a pipescript
        do() generate the script
    """

    _version = "0.35"
    __custom_documentations__ = "pizza.region.coregeometry class"


    def __init__(self,USER=regiondata(),VARIABLES=regiondata(),
                 hasgroup=False, hasmove=False, spacefilling=False):
        """
            constructor of the generic core geometry
                USER: any definitions requires by the geometry
           VARIABLES: variables used to define the geometry (to be used in LAMMPS)
           hasgroup, hasmove: flag to force the sections group and move
           SECTIONS: they must be PIZZA.script

           The flag spacefilling is true of the container of objects (class region) is filled with beads
        """
        self.USER = USER
        self.SECTIONS = {
            'variables': LammpsVariables(VARIABLES,**USER),
               'region': LammpsRegion(**USER),
               'create': LammpsCreate(**USER),
                'group': LammpsGroup(**USER),
             'setgroup': LammpsSetGroup(**USER),
                 'move': LammpsMove(**USER)
            }
        self.FLAGSECTIONS = {
            'variables': True,
               'region': True,
               'create': not spacefilling,
                'group': hasgroup,
             'setgroup': spacefilling,
                 'move': hasmove
            }
        self.spacefilling = spacefilling

    def update(self):
        """ update the USER content for all three scripts """
        if isinstance(self.SECTIONS["variables"],script):
            self.SECTIONS["variables"].USER += self.USER
        if isinstance(self.SECTIONS["region"],script):
            self.SECTIONS["region"].USER += self.USER
        if isinstance(self.SECTIONS["create"],script):
            self.SECTIONS["create"].USER += self.USER
        if isinstance(self.SECTIONS["group"],script):
            self.SECTIONS["group"].USER += self.USER
        if isinstance(self.SECTIONS["setgroup"],script):
            self.SECTIONS["setgroup"].USER += self.USER
        if isinstance(self.SECTIONS["move"],script):
            self.SECTIONS["move"].USER += self.USER


    def copy(self,beadtype=None,name=""):
        """ returns a copy of the graphical object """
        if self.alike != "mixed":
            dup = deepduplicate(self)
            if beadtype != None: # update beadtype
                dup.beadtype = beadtype
            if name != "": # update name
                dup.name = name
            return dup
        else:
            raise ValueError("collections cannot be copied, regenerate the collection instead")


    def creategroup(self):
        """  force the group creation in script """
        self.FLAGSECTIONS["group"] = True

    def setgroup(self):
        """  force the group creation in script """
        self.FLAGSECTIONS["setgroup"] = True

    def createmove(self):
        """  force the fix move creation in script """
        self.FLAGSECTIONS["move"] = True

    def removegroup(self):
        """  force the group creation in script """
        self.FLAGSECTIONS["group"] = False

    def removemove(self):
        """  force the fix move creation in script """
        self.FLAGSECTIONS["move"] = False

    @property
    def hasvariables(self):
        """ return the flag VARIABLES """
        return isinstance(self.SECTIONS["variables"],script) \
               and self.FLAGSECTIONS["variables"]

    @property
    def hasregion(self):
        """ return the flag REGION """
        return isinstance(self.SECTIONS["region"],script) \
               and self.FLAGSECTIONS["region"]

    @property
    def hascreate(self):
        """ return the flag CREATE """
        return isinstance(self.SECTIONS["create"],script) \
               and self.FLAGSECTIONS["create"] \
               and (not self.spacefilling)

    @property
    def hasgroup(self):
        """ return the flag GROUP """
        return isinstance(self.SECTIONS["group"],script) \
               and self.FLAGSECTIONS["group"]

    @property
    def hassetgroup(self):
        """ return the flag GROUP """
        return isinstance(self.SECTIONS["setgroup"],script) \
               and self.FLAGSECTIONS["setgroup"] \
               and self.hasgroup \
               and (not self.hascreate)

    @property
    def hasmove(self):
        """ return the flag MOVE """
        return isinstance(self.SECTIONS["move"],script) \
               and self.FLAGSECTIONS["move"]

    @property
    def isspacefilled(self):
        """ return the flag spacefilling """
        return isinstance(self.SECTIONS["spacefilling"],script) \
               and self.FLAGSECTIONS["spacefilling"]

    @property
    def flags(self):
        """ return a list of all flags that are currently set """
        flag_names = list(self.SECTIONS.keys())
        return [flag for flag in flag_names if getattr(self, f"has{flag}")]

    @property
    def shortflags(self):
        """ return a string made from the first letter of each set flag """
        return "".join([flag[0] for flag in self.flags])


    @property
    def VARIABLES(self):
        """ return variables """
        if isinstance(self.SECTIONS["variables"],script):
            return self.SECTIONS["variables"].VARIABLES
        else:
            v = regiondata()
            for i in range(len(self.SECTIONS["variables"].scripts)):
                v = v + self.SECTIONS["variables"].scripts[i].VARIABLES
            return v

    @property
    def script(self):
        """ generates a pipe script from sections """
        self.update()
        ptmp = self.SECTIONS["variables"] if self.hasvariables else None
        if self.hasregion:
            ptmp = self.SECTIONS["region"] if ptmp is None else ptmp | self.SECTIONS["region"]
        if self.hascreate:
            ptmp = self.SECTIONS["create"] if ptmp is None else ptmp | self.SECTIONS["create"]
        if self.hasgroup:
            ptmp = self.SECTIONS["group"] if ptmp is None else ptmp | self.SECTIONS["group"]
        if self.hassetgroup:
            ptmp = self.SECTIONS["setgroup"] if ptmp is None else ptmp | self.SECTIONS["setgroup"]
        if self.hasmove:
            ptmp = self.SECTIONS["move"] if ptmp is None else ptmp | self.SECTIONS["move"]
        return ptmp
        # before 2023-07-17
        #return self.SECTIONS["variables"] | self.SECTIONS["region"] | self.SECTIONS["create"]

    def do(self,printflag=True):
        """ generates a script """
        p = self.script # intentional, force script before do(), comment added on 2023-07-17
        cmd = self.script.do()
        if printflag: print(cmd)
        return cmd

    def __repr__(self):
        """ display method"""
        nVAR = len(self.VARIABLES)
        print("%s - %s object - beadtype=%d " % (self.name, self.kind,self.beadtype))
        if hasattr(self,"filename"): print(f'\tfilename: "{self.filename}"')
        if nVAR>0:
            print(f"\t<-- {nVAR} variables are defined -->")
            print(f"\tUse {self.name}.VARIABLES to see details and their evaluation")
            for k,v in self.VARIABLES.items():
                v0 = '"'+v+'"' if isinstance(v,str) else repr(v)
                print(wrap(k,"=",v0,20,40,80))
        print("\t<-- keyword arg -->")
        haskeys = False
        for k in ("side","move","units","rotate","open"):
            if k in self.USER:
                v = self.USER.getattr(k)
                if v != "":
                    print(wrap(k,":",v[1:],20,60,80))
                    haskeys = True
        if not haskeys: print(wrap("no keywords","<","from side|move|units|rotate|open",20,60,80))
        flags = self.flags
        if flags: print(f'defined scripts: {span(flags,sep=",")}',"\n")
        return "%s object: %s (beadtype=%d)" % (self.kind,self.name,self.beadtype)


    # ~~~~ validator for region arguments (the implementation is specific and not generic as fix move ones)
    def sidearg(self,side):
        """
            Validation of side arguments for region command (https://docs.lammps.org/region.html)
            side value = in or out
              in = the region is inside the specified geometry
              out = the region is outside the specified geometry
        """
        prefix = "$"
        if side is None:
            return ""
        elif isinstance(side, str):
            side = side.lower()
            if side in ("in","out"):
                return f"{prefix} side {side}"
            elif side in ("","none"):
                return ""
            else:
                raise ValueError(f'the value of side: "{side}" is not recognized')
        else:
            raise ValueError('the parameter side can be "in|out|None"')

    def movearg(self,move):
        """
            Validation of move arguments for region command (https://docs.lammps.org/region.html)
            move args = v_x v_y v_z
              v_x,v_y,v_z = equal-style variables for x,y,z displacement of region over time (distance units)
        """
        prefix = "$"
        if move is None:
            return ""
        elif isinstance(move, str):
            move = move.lower()
            if move in("","none"):
                return ""
            else:
                return f"{prefix} move {move}"
        elif isinstance(move,(list,tuple)):
            if len(move)<3:
                print("NULL will be added to move")
            elif len(move)>3:
                print("move will be truncated to 3 elements")
            movevalid = ["NULL","NULL","NULL"]
            for i in range(min(3,len(move))):
                if isinstance(move[i],str):
                    if move[i].upper()!="NULL":
                        if prefix in move[i]:
                            # we assume a numeric result after evaluation
                            # Pizza variables will be evaluated
                            # formateval for the evaluation of ${}
                            # eval for residual expressions
                            movevalid[i] = round(eval(self.VARIABLES.formateval(move[i])),6)
                        else:
                            # we assume a variable (LAMMPS variable, not Pizza ones)
                            movevalid[i] = "v_" + move[i]
                elif not isinstance(move[i],(int,float)):
                    if (move[i] is not None):
                        raise TypeError("move values should be str, int or float")
            return f"{prefix} move {span(movevalid)}"
        else:
            raise TypeError("the parameter move should be a list or tuple")

    def unitsarg(self,units):
        """
            Validation for units arguments for region command (https://docs.lammps.org/region.html)
            units value = lattice or box
              lattice = the geometry is defined in lattice units
              box = the geometry is defined in simulation box units
        """
        prefix = "$"
        if units is None:
            return ""
        elif isinstance(units,str):
            units = units.lower()
            if units in ("lattice","box"):
                return f"{prefix} units {units}"
            elif (units=="") or (units=="none"):
                return ""
            else:
                raise ValueError(f'the value of side: "{units}" is not recognized')
        else:
            raise TypeError('the parameter units can be "lattice|box|None"')

    def rotatearg(self,rotate):
        """
            Validation of rotate arguments for region command (https://docs.lammps.org/region.html)
            rotate args = v_theta Px Py Pz Rx Ry Rz
              v_theta = equal-style variable for rotaton of region over time (in radians)
              Px,Py,Pz = origin for axis of rotation (distance units)
              Rx,Ry,Rz = axis of rotation vector
        """
        prefix = "$"
        if rotate is None:
            return ""
        elif isinstance(rotate, str):
            rotate = rotate.lower()
            if rotate in ("","none",None):
                return ""
            else:
                return f"{prefix} rotate {rotate}"
        elif isinstance(rotate,(list,tuple)):
            if len(rotate)<7:
                print("NULL will be added to rotate")
            elif len(rotate)>7:
                print("rotate will be truncated to 7 elements")
            rotatevalid = ["NULL"]*7
            for i in range(min(7,len(rotate))):
                if isinstance(rotate[i],str):
                    if rotate[i].upper()!="NULL":
                        if prefix in rotate[i]:
                            rotatevalid[i] = round(eval(self.VARIABLES.formateval(rotate[i])),6)
                        else:
                            rotatevalid[i] = rotate[i]
                elif not isinstance(rotate[i],(int,float)):
                    if (rotate[i] is not None):
                        raise TypeError("rotate values should be str, int or float")
            return f"{prefix} move {span(rotatevalid)}"
        else:
            raise TypeError("the parameter rotate should be a list or tuple")

    def openarg(self,open):
        """
            Validation of open arguments for region command (https://docs.lammps.org/region.html)
            open value = integer from 1-6 corresponding to face index (see below)
            The indices specified as part of the open keyword have the following meanings:

            For style block, indices 1-6 correspond to the xlo, xhi, ylo, yhi, zlo, zhi surfaces of the block.
            I.e. 1 is the yz plane at x = xlo, 2 is the yz-plane at x = xhi, 3 is the xz plane at y = ylo,
            4 is the xz plane at y = yhi, 5 is the xy plane at z = zlo, 6 is the xy plane at z = zhi).
            In the second-to-last example above, the region is a box open at both xy planes.

            For style prism, values 1-6 have the same mapping as for style block.
            I.e. in an untilted prism, open indices correspond to the xlo, xhi, ylo, yhi, zlo, zhi surfaces.

            For style cylinder, index 1 corresponds to the flat end cap at the low coordinate along the cylinder axis,
            index 2 corresponds to the high-coordinate flat end cap along the cylinder axis, and index 3 is the curved
            cylinder surface. For example, a cylinder region with open 1 open 2 keywords will be open at both ends
            (e.g. a section of pipe), regardless of the cylinder orientation.
        """
        prefix = "$"
        if open in ("","none",None):
            return ""
        elif isinstance(open, str):
            raise TypeError(" the parameter open should be an integer or a list/tuple of integers from 1-6")
        elif isinstance(open, int):
            if open in range(1,7):
                return f"{prefix} open {open}"
            else:
                raise TypeError(" open value should be integer from 1-6")
        elif isinstance(open, (list,tuple)):
            openvalid = [f"{prefix} open {i}" for i in range(1,7) if i in open]
            return f"$ {span(openvalid)}"
    # ~~~~ end validator for region arguments

    # ~~~~ validator for fix move arguments (implemented generically on 2023-07-17)
    def fixmoveargvalidator(self, argtype, arg, arglen):
        """
            Validation of arguments for fix move command in LAMMPS (https://docs.lammps.org/fix_move.html)

            LAMMPS syntax:
                fix ID group-ID move style args
                - linear args = Vx Vy Vz
                - wiggle args = Ax Ay Az period
                - rotate args = Px Py Pz Rx Ry Rz period
                - transrot args = Vx Vy Vz Px Py Pz Rx Ry Rz period
                - variable args = v_dx v_dy v_dz v_vx v_vy v_vz

            Args:
                argtype: Type of the argument (linear, wiggle, rotate, transrot, variable)
                arg: The argument to validate
                arglen: Expected length of the argument
        """
        prefix = "$"
        if arg in ("","none",None):
            return ""
        elif isinstance(arg,(list,tuple)):
            if len(arg) < arglen:
                print(f"NULL will be added to {argtype}")
            elif len(arg) > arglen:
                print(f"{argtype} will be truncated to {arglen} elements")
            argvalid = ["NULL"]*arglen
            for i in range(min(arglen,len(arg))):
                if isinstance(arg[i],str):
                    if arg[i].upper()!="NULL":
                        if prefix in arg[i]:
                            argvalid[i] = round(eval(self.VARIABLES.formateval(arg[i])),6)
                        else:
                            argvalid[i] = arg[i]
                elif not isinstance(arg[i],(int,float)):
                    if (arg[i] is not None):
                        raise TypeError(f"{argtype} values should be str, int or float")
            return f"{prefix} move {span(argvalid)}"
        else:
            raise TypeError(f"the parameter {argtype} should be a list or tuple")


    def fixmoveargs(self, linear=None, wiggle=None, rotate=None, transrot=None, variable=None):
        """
            Validates all arguments for fix move command in LAMMPS (https://docs.lammps.org/fix_move.html)
            the result is adictionary, all fixmove can be combined
        """
        argsdict = {
            "linear": [linear, 3],
            "wiggle": [wiggle, 4],
            "rotate": [rotate, 7],
            "transrot": [transrot, 10],
            "variable": [variable, 6]
        }

        for argtype, arginfo in argsdict.items():
            arg, arglen = arginfo
            if arg is not None:
                argsdict[argtype] = self.fixmoveargvalidator(argtype, arg, arglen)
        return argsdict


    def get_fixmovesyntax(self, argtype=None):
        """
        Returns the syntax for LAMMPS command, or detailed explanation for a specific argument type

        Args:
        argtype: Optional; Type of the argument (linear, wiggle, rotate, transrot, variable)
        """
        syntax = {
            "linear": "linear args = Vx Vy Vz\n"
                      "Vx,Vy,Vz = components of velocity vector (velocity units), any component can be specified as NULL",
            "wiggle": "wiggle args = Ax Ay Az period\n"
                       "Ax,Ay,Az = components of amplitude vector (distance units), any component can be specified as NULL\n"
                       "period = period of oscillation (time units)",
            "rotate": "rotate args = Px Py Pz Rx Ry Rz period\n"
                       "Px,Py,Pz = origin point of axis of rotation (distance units)\n"
                       "Rx,Ry,Rz = axis of rotation vector\n"
                       "period = period of rotation (time units)",
            "transrot": "transrot args = Vx Vy Vz Px Py Pz Rx Ry Rz period\n"
                        "Vx,Vy,Vz = components of velocity vector (velocity units)\n"
                        "Px,Py,Pz = origin point of axis of rotation (distance units)\n"
                        "Rx,Ry,Rz = axis of rotation vector\n"
                        "period = period of rotation (time units)",
            "variable": "variable args = v_dx v_dy v_dz v_vx v_vy v_vz\n"
                        "v_dx,v_dy,v_dz = 3 variable names that calculate x,y,z displacement as function of time, any component can be specified as NULL\n"
                        "v_vx,v_vy,v_vz = 3 variable names that calculate x,y,z velocity as function of time, any component can be specified as NULL",
        }

        base_syntax = (
            "fix ID group-ID move style args\n"
            " - linear args = Vx Vy Vz\n"
            " - wiggle args = Ax Ay Az period\n"
            " - rotate args = Px Py Pz Rx Ry Rz period\n"
            " - transrot args = Vx Vy Vz Px Py Pz Rx Ry Rz period\n"
            " - variable args = v_dx v_dy v_dz v_vx v_vy v_vz\n\n"
            'use get_movesyntax("movemethod") for details'
            "manual: https://docs.lammps.org/fix_move.html"
        )

        return syntax.get(argtype, base_syntax)

    # ~~~~ end validator for fix move arguments

    def __add__(self,C):
        """ overload addition ("+") operator """
        if isinstance(C,coregeometry):
            dup = deepduplicate(self)
            dup.name = cleanname(self.name) +"+"+ cleanname(C.name)
            dup.USER = dup.USER + C.USER
            dup.USER.ID = "$" + cleanname(self.USER.ID) +"+"+ cleanname(C.USER.ID)
            dup.SECTIONS["variables"] = dup.SECTIONS["variables"] + C.SECTIONS["variables"]
            dup.SECTIONS["region"] = dup.SECTIONS["region"] + C.SECTIONS["region"]
            dup.SECTIONS["create"] = dup.SECTIONS["create"] + C.SECTIONS["create"]
            dup.SECTIONS["group"] = dup.SECTIONS["group"] + C.SECTIONS["group"]
            dup.SECTIONS["move"] = dup.SECTIONS["move"] + C.SECTIONS["move"]
            dup.FLAGSECTIONS["variables"] = dup.FLAGSECTIONS["variables"] or C.FLAGSECTIONS["variables"]
            dup.FLAGSECTIONS["region"] = dup.FLAGSECTIONS["region"] or C.FLAGSECTIONS["region"]
            dup.FLAGSECTIONS["create"] = dup.FLAGSECTIONS["create"] or C.FLAGSECTIONS["create"]
            dup.FLAGSECTIONS["group"] = dup.FLAGSECTIONS["group"] or C.FLAGSECTIONS["group"]
            dup.FLAGSECTIONS["move"] = dup.FLAGSECTIONS["move"] or C.FLAGSECTIONS["move"]
            return dup
        raise TypeError("the second operand must a region.coregeometry object")

    def __iadd__(self,C):
        """ overload iaddition ("+=") operator """
        if isinstance(C,coregeometry):
            self.USER += C.USER
            self.SECTIONS["variables"] += C.SECTIONS["variables"]
            self.SECTIONS["region"] += C.SECTIONS["region"]
            self.SECTIONS["create"] += C.SECTIONS["create"]
            self.SECTIONS["group"] += C.SECTIONS["group"]
            self.SECTIONS["move"] += C.SECTIONS["move"]
            self.FLAGSECTIONS["variables"] = self.FLAGSECTIONS["variables"] or C.FLAGSECTIONS["variables"]
            self.FLAGSECTIONS["region"] = self.FLAGSECTIONS["region"] or C.FLAGSECTIONS["region"]
            self.FLAGSECTIONS["create"] = self.FLAGSECTIONS["create"] or C.FLAGSECTIONS["create"]
            self.FLAGSECTIONS["group"] = self.FLAGSECTIONS["group"] or C.FLAGSECTIONS["group"]
            self.FLAGSECTIONS["move"] = self.FLAGSECTIONS["move"] or C.FLAGSECTIONS["move"]
            return self
        raise TypeError("the operand must a region.coregeometry object")

    def __or__(self,C):
        """ overload | pipe """
        if isinstance(C,coregeometry):
            dup = deepduplicate(self)
            dup.name = cleanname(self.name) +"|"+ cleanname(C.name)
            dup.USER = dup.USER + C.USER
            dup.USER.ID = "$" + cleanname(self.USER.ID) +"|"+ cleanname(C.USER.ID)
            dup.SECTIONS["variables"] = dup.SECTIONS["variables"] | C.SECTIONS["variables"]
            dup.SECTIONS["region"] = dup.SECTIONS["region"] | C.SECTIONS["region"]
            dup.SECTIONS["create"] = dup.SECTIONS["create"] | C.SECTIONS["create"]
            dup.SECTIONS["group"] = dup.SECTIONS["group"] | C.SECTIONS["group"]
            dup.SECTIONS["move"] = dup.SECTIONS["move"] | C.SECTIONS["move"]
            self.FLAGSECTIONS["variables"] = self.FLAGSECTIONS["variables"] or C.FLAGSECTIONS["variables"]
            self.FLAGSECTIONS["region"] = self.FLAGSECTIONS["region"] or C.FLAGSECTIONS["region"]
            self.FLAGSECTIONS["create"] = self.FLAGSECTIONS["create"] or C.FLAGSECTIONS["create"]
            self.FLAGSECTIONS["group"] = self.FLAGSECTIONS["group"] or C.FLAGSECTIONS["group"]
            self.FLAGSECTIONS["move"] = self.FLAGSECTIONS["move"] or C.FLAGSECTIONS["move"]
            return dup
        raise TypeError("the second operand must a region.coregeometry object")

    # copy and deep copy methods for the class (required)
    def __getstate__(self):
        """ getstate for cooperative inheritance / duplication """
        return self.__dict__.copy()

    def __setstate__(self,state):
        """ setstate for cooperative inheritance / duplication """
        self.__dict__.update(state)

    def __copy__(self):
        """ copy method """
        cls = self.__class__
        copie = cls.__new__(cls)
        copie.__dict__.update(self.__dict__)
        return copie

    def __deepcopy__(self, memo):
        """ deep copy method """
        cls = self.__class__
        copie = cls.__new__(cls)
        memo[id(self)] = copie
        for k, v in self.__dict__.items():
            setattr(copie, k, deepduplicate(v, memo)) # replace duplicatedeep by deepduplicate (OV: 2023-07-28)
        return copie

class Block(coregeometry):
    """ Block class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "block%03d" % counter[1]
        self.kind = "block"     # kind of object
        self.alike = "block"    # similar object for plotting
        self.beadtype = 1       # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$block"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Cone(coregeometry):
    """ Cone class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "cone%03d" % counter[1]
        self.kind = "cone"     # kind of object
        self.alike = "cone"    # similar object for plotting
        self.beadtype = 1      # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$cone"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Cylinder(coregeometry):
    """ Cylinder class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "cylinder%03d" % counter[1]
        self.kind = "cylinder"     # kind of object
        self.alike = "cylinder"    # similar object for plotting
        self.beadtype = 1          # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$cylinder"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Ellipsoid(coregeometry):
    """ Ellipsoid class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "ellipsoid%03d" % counter[1]
        self.kind = "ellipsoid"     # kind of object
        self.alike = "ellipsoid"    # similar object for plotting
        self.beadtype = 1           # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$ellipsoid"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Plane(coregeometry):
    """ Plane class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "plane%03d" % counter[1]
        self.kind = "plane"      # kind of object
        self.alike = "plane"     # similar object for plotting
        self.beadtype = 1       # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$plane"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Prism(coregeometry):
    """ Prism class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "prism%03d" % counter[1]
        self.kind = "prism"      # kind of object
        self.alike = "prism"     # similar object for plotting
        self.beadtype = 1       # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$prism"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Sphere(coregeometry):
    """ Sphere class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "sphere%03d" % counter[1]
        self.kind = "sphere"      # kind of object
        self.alike = "ellipsoid"     # similar object for plotting
        self.beadtype = 1       # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$sphere"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Union(coregeometry):
    """ Union class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "union%03d" % counter[1]
        self.kind = "union"      # kind of object
        self.alike = "operator"     # similar object for plotting
        self.beadtype = 1       # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$union"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Intersect(coregeometry):
    """ Intersect class """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False,**variables):
        self.name = "intersect%03d" % counter[1]
        self.kind = "intersect"      # kind of object
        self.alike = "operator"     # similar object for plotting
        self.beadtype = 1       # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        # call the generic constructor
        super().__init__(
                USER = regiondata(style="$intersect"),
                VARIABLES = regiondata(**variables),
                hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling
                )

class Evalgeometry(coregeometry):
    """ generic class to store evaluated objects with region.eval() """

    def __init__(self,counter,index=None,subindex=None,
                 hasgroup=False,hasmove=False,spacefilling=False):
        self.name = "eval%03d" % counter[1]
        self.kind = "eval"      # kind of object
        self.alike = "eval"     # similar object for plotting
        self.beadtype = 1       # bead type
        self.index = counter[0] if index is None else index
        self.subindex = subindex
        super().__init__(hasgroup=hasgroup,hasmove=hasmove,spacefilling=spacefilling)


class Collection:
    """
        Collection class (including many objects)
    """
    _version = "0.31"
    __custom_documentations__ = "pizza.region.Collection class"

    # CONSTRUCTOR
    def __init__(self,counter,
                 name=None,
                 index = None,
                 subindex = None,
                 hasgroup = False,
                 USER = regiondata()):
        if (name is None) or (name==""):
            self.name = "collect%03d" % counter[1]
        elif name in self:
            raise KeyError(f'the name "{name}" already exist')
        else:
            self.name = name
        if not isinstance(USER,regiondata):
            raise TypeError("USER should be a regiondata object")
        USER.groupID = "$"+self.name # the content is frozen
        USER.ID = ""
        self.USER = USER
        self.kind = "collection"    # kind of object
        self.alike = "mixed"        # similar object for plotting
        self.index = counter[0] if index is None else index
        self.subindex = counter[1]
        self.collection = regioncollection()
        self.SECTIONS = {
        	'group': LammpsCollectionGroup(**USER)
        }
        self.FLAGSECTIONS = {"group": hasgroup}

    def update(self):
        """ update the USER content for the script """
        if isinstance(self.SECTIONS["group"],script):
            self.USER.ID = "$"\
                +span([groupprefix+x for x in self.list()]) # the content is frozen
            self.SECTIONS["group"].USER += self.USER

    def creategroup(self):
        """  force the group creation in script """
        for o in self.collection: o.creategroup()
        self.update()
        self.FLAGSECTIONS["group"] = True

    def removegroup(self,recursive=True):
        """  force the group creation in script """
        if recursive:
            for o in self.collection: o.removegroup()
        self.FLAGSECTIONS["group"] = False

    @property
    def hasgroup(self):
        """ return the flag hasgroup """
        return self.FLAGSECTIONS["group"]

    @property
    def flags(self):
        """ return a list of all flags that are currently set """
        flag_names = list(self.SECTIONS.keys())
        return [flag for flag in flag_names if getattr(self, f"has{flag}")]

    @property
    def shortflags(self):
        """ return a string made from the first letter of each set flag """
        return "".join([flag[0] for flag in self.flags])

    @property
    def script(self):
        """ generates a pipe script from SECTIONS """
        self.update()
        return self.SECTIONS["group"]

    def __repr__(self):
        keylengths = [len(key) for key in self.collection.keys()]
        width = max(10,max(keylengths)+2)
        fmt = "%%%ss:" % width
        line = ( fmt % ('-'*(width-2)) ) + ( '-'*(min(40,width*5)) )
        print(line,"  %s - %s object" % (self.name, self.kind), line,sep="\n")
        for key,value in self.collection.items():
            flags = "("+self.collection[key].shortflags+")" if self.collection[key].flags else "(no script)"
            print(fmt % key,value.kind,
                  '"%s"' % value.name," > ",flags)
        flags = self.flags
        if flags: print(line,f'defined scripts: {span(flags,sep=",")}',sep="\n")
        print(line)
        return "%s object: %s (beadtype=[%s])" % (self.kind,self.name,", ".join(map(str,self.beadtype)))

    # GET -----------------------------
    def get(self,name):
        """ returns the object """
        if name in self.collection:
            return self.collection.getattr(name)
        elif name in ["collection","hasgroup","flags","shortflags","script"]:
            return getattr(self,name)
        else:
            raise ValueError('the object "%s" does not exist, use list()' % name)

    # GETATTR --------------------------
    def __getattr__(self,key):
        """ get attribute override """
        return self.get(key)

    @property
    def beadtype(self):
        """ returns the beadtypes used in the collection """
        b = []
        for o in self.collection:
            if o.beadtype not in b:
                b.append(o.beadtype)
        if len(b)==0:
            return 1
        else:
            return b

    # GROUP -------------------------------
    def group(self):
        """ return the grouped coregeometry object """
        if len(self) == 0:return pipescript()
        # execute all objects
        for i in range(len(self)): self.collection[i].do()
        # concatenate all objects into a pipe script
        liste = [x.SECTIONS["variables"] for x in self.collection if x.hasvariables] + \
                [x.SECTIONS["region"]    for x in self.collection if x.hasregion] + \
                [x.SECTIONS["create"]    for x in self.collection if x.hascreate] + \
                [x.SECTIONS["group"]     for x in self.collection if x.hasgroup] + \
                [x.SECTIONS["setgroup"]  for x in self.collection if x.hassetgroup] + \
                [x.SECTIONS["move"]      for x in self.collection if x.hasmove]
        return pipescript.join(liste)

    # LEN ---------------------------------
    def __len__(self):
        """ return length of collection """
        return len(self.collection)

    # LIST ---------------------------------
    def list(self):
        """ return the list of objects """
        return self.collection.keys()



# %% region class (main class)
class region:
    """
        region main class
        assuming a simulation box centered 0,0,0
        and of size: width x height x depth

        Attributes:
        ----------
        name : str, optional
            Name of the region (default is 'region container').
        nbeads : int, optional
            Number of beads in the region (default is 1).
        run : int, optional
            Run configuration parameter (default is 1).
        mass : float, optional
            Mass of the region (default is 1).
        volume : float, optional
            Volume of the region (default is 1).
        radius : float, optional
            Radius of the region (default is 1.5).
        contactradius : float, optional
            Contact radius of the region (default is 0.5).
        velocities : list of floats, optional
            Velocities configuration (default is [0, 0, 0]).
        forces : list of floats, optional
            Forces configuration (default is [0, 0, 0]).
        filename : str, optional
            Name of the output file (default is an empty string, which leads to naming based on the region name).
        index : int, optional
            Index or identifier for the region.
        width : float, optional
            Width of the region (default is 10).
        height : float, optional
            Height of the region (default is 10).
        depth : float, optional
            Depth of the region (default is 10).
        units: str, optional
            Units for create_box (default is "")
        hasfixmove : bool, optional
            Indicates if the region has a fix move (default is False).
        livepreview_options : dict, optional
            Configuration for live preview, with 'static' and 'dynamic' options (default values provided).
        spacefilling : bool, optional
            Indicates if the design is space-filling (default is False).
        fillingbeadtype : int, optional
            Type of bead used for space filling (default is 1).

    """
    _version = "0.36"
    __custom_documentations__ = "pizza.region.region class"

    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
    #
    # CONSTRUCTOR METHOD
    #
    #
    # The constructor include
    #   the main container: objects (a dictionnary)
    #   several attributes covering current and future use of PIZZA.REGION()
    #
    # The original constructor is derived from PIZZA.RASTER() with
    # an intent to allow at some point some forward and backward port between
    # objects of the class PIZZA.RASTER() and PIZZA.REGION().
    #
    # The code will evolve according to the needs, please come back regularly.
    #
    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-

    # CONSTRUCTOR ----------------------------
    def __init__(self,
                 # region properties
                 name="region container",
                 nbeads=1,
                 run=1,
                 # for data conversion (not implemented for now)
                 mass=1,
                 volume=1,
                 radius=1.5,
                 contactradius=0.5,
                 velocities=[0,0,0],
                 forces=[0,0,0],
                 # other properties
                 filename="",
                 index = None,
                 width = 10,
                 height = 10,
                 depth = 10,
                 units = "",
                 hasfixmove = False, # by default no fix move
                 # livepreview options
                 livepreview_options = {
                     'static':{'run':1},
                     'dynamic':{'run':100}
                     },
                 # spacefilling design (added on 2023-08-10)
                 spacefilling = False,
                 fillingbeadtype = 1
                 ):
        """ constructor """
        self.name = name
        # live data
        self.live = regiondata(nbeads=nbeads,
                               run=run,
                               width=width,
                               height=height,
                               depth=depth)
        # generic SMD properties (to be rescaled)
        self.volume = volume
        self.mass = mass
        self.radius = radius
        self.contactradius = contactradius
        self.velocities = velocities
        self.forces =forces
        if filename == "":
            self.filename = "region (%s)" % self.name
        else:
            self.filename = filename
        self.index = index
        self.objects = {}    # object container
        self.nobjects = 0    # total number of objects (alive)
        # count objects per type
        self.counter = {
                  "ellipsoid":0,
                  "block":0,
                  "sphere":0,
                  "cone":0,
                  "cylinder":0,
                  "prism":0,
                  "plane":0,
                  "union":0,
                  "intersect":0,
                  "eval":0,
                  "collection":0,
                  "all":0
            }
        # fix move flag
        self.hasfixmove = hasfixmove
        # livelammps (for live sessions) - added 2023-02-06
        self.livelammps = {
            "URL": livelammpsURL,
         "active": False,
           "file": None,
        "options": livepreview_options
            }
        # space filling  added 2023-08-10
        self.spacefilling = {
            "flag": spacefilling,
    "fillingstyle": "$block",
 "fillingbeadtype": fillingbeadtype,
    "fillingwidth": width,
   "fillingheight": height,
    "fillingdepth": depth,
    "fillingunits": units
         }


    # space filling attributes (cannot be changed)
    @property
    def isspacefilled(self):
        return self.spacefilling["flag"]

    @property
    def spacefillingbeadtype(self):
        return self.spacefilling["fillingbeadtype"]

    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
    #
    # REGION.GEOMETRY constructors
    #
    #
    #   These methods create the 3D geometry objects (at least their code)
    #   A geometry is a collection of PIZZA.SCRIPT() objects (LAMMPS codelet)
    #   not a real geometry. The distinction between the creation (definition)
    #   and the execution (generation) of the gometry object existed already
    #   in PIZZA.RASTER(), but here they remain codelets as ONLY LAMMPS can
    #   generate the real object.
    #
    #   This level of abstraction makes it possible to mix PIZZA variables
    #   (USER, PIZZA.SCRIPT.USER, PIZZA.PIPESCRIPT.USER) with LAMMPS variables.
    #   The same object template can be used in different LAMMPS scripts with
    #   different values and without writting additional Python code.
    #   In shorts: USER fields store PIZZA.SCRIPT() like variables
    #              (they are compiled [statically] before LAMMPS execution)
    #              VARIABLES are defined in the generated LAMMPS script but
    #              created [dynamically] in LAMMPS. Note that these variables
    #              are defined explicitly with the LAMMPS variable command:
    #                   variable name style args ...
    #   Note: static variables can have only one single value for LAMMPS, which
    #         is known before LAMMPS is launched. The others can be assigned
    #         at runtime when LAMMPS is running.
    #   Example with complex definitions
    #       R.ellipsoid(0,0,0,1,1,1,name="E2",side="out",
    #                   move=["left","${up}*3",None],
    #                   up=0.1)
    #       R.E2.VARIABLES.left = '"swiggle(%s,%s,%s)"%(${a},${b},${c})'
    #       R.E2.VARIABLES.a="${b}-5"
    #       R.E2.VARIABLES.b=5
    #       R.E2.VARIABLES.c=100
    #
    #   The methods PIZZA.REGION.DO(), PIZZA.REGION.DOLIVE() compiles
    #   (statically) and generate the corresponding LAMMPS code. The static
    #   compiler accepts hybrid constructions where USER and VARIABLES are
    #   mixed. Any undefined variables will be assumed to be defined elsewhere
    #   in the LAMMPS code.
    #
    #  Current attributes of PIZZA.REGION.OBJECT cover current and future use
    #  of these objects and will allow some point some forward and backward
    #  compatibility with the same PIZZA.RASTER.OBJECT.
    #
    #
    #   References:
    #       https://docs.lammps.org/region.html
    #       https://docs.lammps.org/variable.html
    #       https://docs.lammps.org/create_atoms.html
    #       https://docs.lammps.org/create_box.html
    #
    #
    #   List of implemented geometries (shown here with the LAMMPS syntax)
    #       block args = xlo xhi ylo yhi zlo zhi
    #       cone args = dim c1 c2 radlo radhi lo hi
    #       cylinder args = dim c1 c2 radius lo hi
    #       ellipsoid args = x y z a b c <-- first method to be implemented
    #       plane args = px py pz nx ny n
    #       prism args = xlo xhi ylo yhi zlo zhi xy xz yz
    #       sphere args = x y z radius
    #       union args = N reg-ID1 reg-ID2 ..
    #       intersect args = N reg-ID1 reg-ID2 ...
    #
    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-

    # BLOCK method ---------------------------
    # block args = xlo xhi ylo yhi zlo zhi
    # xlo,xhi,ylo,yhi,zlo,zhi = bounds of block in all dimensions (distance units)
    def block(self,xlo=-5,xhi=5,ylo=-5,yhi=5,zlo=-5,zhi=5,
                  name=None,beadtype=None,fake=False,
                  side=None,units=None,move=None,rotate=None,open=None,
                  index = None,subindex = None,
                  **variables
                  ):
        """
        creates a block region
            xlo,xhi,ylo,yhi,zlo,zhi = bounds of block in all dimensions (distance units)

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "block001"
            beadtype = 1
                fake = False (use True to test the execution)
     index, subindex = object index and subindex

            Extra properties
                side = "in|out"
               units = "lattice|box"
                move = "[${v1} ${v2} ${v3}]" or [v1,v2,v3] as a list
                       with v1,v2,v3 equal-style variables for x,y,z displacement
                       of region over time (distance units)
              rotate = string or 1x7 list (see move) coding for vtheta Px Py Pz Rx Ry Rz
                       vtheta = equal-style variable for rotation of region over time (in radians)
                       Px,Py,Pz = origin for axis of rotation (distance units)
                       Rx,Ry,Rz = axis of rotation vector
                open = integer from 1-6 corresponding to face index

            See examples for elliposid()
        """
        # prepare object creation
        kind = "block"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object C with C for cone
        B = Block((self.counter["all"]+1,self.counter[kind]+1),
                      spacefilling=self.isspacefilled, # added on 2023-08-11
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): B.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: B.beadtype = beadtype # bead type (if not defined, default index will apply)
        B.USER.ID = "$"+B.name        # add $ to prevent its execution
        B.USER.args = [xlo,xhi,ylo,yhi,zlo,zhi]   # args = [....] as defined in the class Block
        B.USER.beadtype = B.beadtype  # beadtype to be used for create_atoms
        B.USER.side = B.sidearg(side) # extra parameter side
        B.USER.move = B.movearg(move) # move arg
        B.USER.units = B.unitsarg(units) # units
        B.USER.rotate = B.rotatearg(rotate) # rotate
        B.USER.open = B.openarg(open) # open
        # Create the object if not fake
        if fake:
            return B
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = B
            self.nobjects += 1
            return None

    # CONE method ---------------------------
    # cone args = dim c1 c2 radlo radhi lo hi
    # dim = x or y or z = axis of cone
    # c1,c2 = coords of cone axis in other 2 dimensions (distance units)
    # radlo,radhi = cone radii at lo and hi end (distance units)
    # lo,hi = bounds of cone in dim (distance units)
    def cone(self,dim="z",c1=0,c2=0,radlo=2,radhi=5,lo=-10,hi=10,
                  name=None,beadtype=None,fake=False,
                  side=None,units=None,move=None,rotate=None,open=None,
                  index = None,subindex = None,
                  **variables
                  ):
        """
        creates a cone region
            dim = "x" or "y" or "z" = axis of the cone
                 note: USER, LAMMPS variables are not authorized here
            c1,c2 = coords of cone axis in other 2 dimensions (distance units)
            radlo,radhi = cone radii at lo and hi end (distance units)
            lo,hi = bounds of cone in dim (distance units)

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "cone001"
            beadtype = 1
                fake = False (use True to test the execution)
     index, subindex = object index and subindex

            Extra properties
                side = "in|out"
               units = "lattice|box"
                move = "[${v1} ${v2} ${v3}]" or [v1,v2,v3] as a list
                       with v1,v2,v3 equal-style variables for x,y,z displacement
                       of region over time (distance units)
              rotate = string or 1x7 list (see move) coding for vtheta Px Py Pz Rx Ry Rz
                       vtheta = equal-style variable for rotation of region over time (in radians)
                       Px,Py,Pz = origin for axis of rotation (distance units)
                       Rx,Ry,Rz = axis of rotation vector
                open = integer from 1-6 corresponding to face index

            See examples for elliposid()
        """
        # prepare object creation
        kind = "cone"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object C with C for cone
        C = Cone((self.counter["all"]+1,self.counter[kind]+1),
                      spacefilling=self.isspacefilled, # added on 2023-08-11
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): C.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: C.beadtype = beadtype # bead type (if not defined, default index will apply)
        C.USER.ID = "$"+C.name        # add $ to prevent its execution
        C.USER.args = [dim,c1,c2,radlo,radhi,lo,hi]   # args = [....] as defined in the class Cone
        C.USER.beadtype = C.beadtype  # beadtype to be used for create_atoms
        C.USER.side = C.sidearg(side) # extra parameter side
        C.USER.move = C.movearg(move) # move arg
        C.USER.units = C.unitsarg(units) # units
        C.USER.rotate = C.rotatearg(rotate) # rotate
        C.USER.open = C.openarg(open) # open
        # Create the object if not fake
        if fake:
            return C
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = C
            self.nobjects += 1
            return None

    # CYLINDER method ---------------------------
    # cylinder args = dim c1 c2 radius lo hi
    # dim = x or y or z = axis of cylinder
    # c1,c2 = coords of cylinder axis in other 2 dimensions (distance units)
    # radius = cylinder radius (distance units)
    # c1,c2, and radius can be a variable (see below)
    # lo,hi = bounds of cylinder in dim (distance units)
    def cylinder(self,dim="z",c1=0,c2=0,radius=4,lo=-10,hi=10,
                  name=None,beadtype=None,fake=False,
                  side=None,units=None,move=None,rotate=None,open=None,
                  index = None,subindex = None,
                  **variables
                  ):
        """
        creates a cone region
              dim = x or y or z = axis of cylinder
              c1,c2 = coords of cylinder axis in other 2 dimensions (distance units)
              radius = cylinder radius (distance units)
              c1,c2, and radius can be a LAMMPS variable
              lo,hi = bounds of cylinder in dim (distance units)

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "cylinder001"
            beadtype = 1
                fake = False (use True to test the execution)
     index, subindex = object index and subindex

            Extra properties
                side = "in|out"
               units = "lattice|box"
                move = "[${v1} ${v2} ${v3}]" or [v1,v2,v3] as a list
                       with v1,v2,v3 equal-style variables for x,y,z displacement
                       of region over time (distance units)
              rotate = string or 1x7 list (see move) coding for vtheta Px Py Pz Rx Ry Rz
                       vtheta = equal-style variable for rotation of region over time (in radians)
                       Px,Py,Pz = origin for axis of rotation (distance units)
                       Rx,Ry,Rz = axis of rotation vector
                open = integer from 1-6 corresponding to face index

            See examples for elliposid()
        """
        # prepare object creation
        kind = "cylinder"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object C with C for cylinder
        C = Cylinder((self.counter["all"]+1,self.counter[kind]+1),
                      spacefilling=self.isspacefilled, # added on 2023-08-11
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): C.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: C.beadtype = beadtype # bead type (if not defined, default index will apply)
        C.USER.ID = "$"+C.name        # add $ to prevent its execution
        C.USER.args = [dim,c1,c2,radius,lo,hi]   # args = [....] as defined in the class Cylinder
        C.USER.beadtype = C.beadtype  # beadtype to be used for create_atoms
        C.USER.side = C.sidearg(side) # extra parameter side
        C.USER.move = C.movearg(move) # move arg
        C.USER.units = C.unitsarg(units) # units
        C.USER.rotate = C.rotatearg(rotate) # rotate
        C.USER.open = C.openarg(open) # open
        # Create the object if not fake
        if fake:
            return C
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = C
            self.nobjects += 1
            return None

    # ELLIPSOID method ---------------------------
    # ellipsoid args = x y z a b c
    # x,y,z = center of ellipsoid (distance units)
    # a,b,c = half the length of the principal axes of the ellipsoid (distance units)
    # x,y,z,a,b,c can be variables
    def ellipsoid(self,x=0,y=0,z=0,a=5,b=3,c=2,
                  name=None,beadtype=None,fake=False,
                  side=None,units=None,move=None,rotate=None,open=None,
                  index = None,subindex = None,
                  **variables
                  ):
        """
        creates an ellipsoid region
            ellipsoid(x,y,z,a,b,c [,name=None,beadtype=None,property=value,...])
            x,y,z = center of ellipsoid (distance units)
            a,b,c = half the length of the principal axes of the ellipsoid (distance units)

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "ellipsoid001"
            beadtype = 1
                fake = False (use True to test the execution)
                index, subindex = object index and subindex

            Extra properties
                side = "in|out"
               units = "lattice|box"
                move = "[${v1} ${v2} ${v3}]" or [v1,v2,v3] as a list
                       with v1,v2,v3 equal-style variables for x,y,z displacement
                       of region over time (distance units)
              rotate = string or 1x7 list (see move) coding for vtheta Px Py Pz Rx Ry Rz
                       vtheta = equal-style variable for rotation of region over time (in radians)
                       Px,Py,Pz = origin for axis of rotation (distance units)
                       Rx,Ry,Rz = axis of rotation vector
                open = integer from 1-6 corresponding to face index


            Examples:
                # example with variables created either at creation or later
                    R = region(name="my region")
                    R.ellipsoid(0, 0, 0, 1, 1, 1,name="E1",toto=3)
                    repr(R.E1)
                    R.E1.VARIABLES.a=1
                    R.E1.VARIABLES.b=2
                    R.E1.VARIABLES.c="(${a},${b},100)"
                    R.E1.VARIABLES.d = '"%s%s" %("test",${c}) # note that test could be replaced by any function'
                # example with extra parameters
                    R.ellipsoid(0,0,0,1,1,1,name="E2",side="out",move=["left","${up}*3",None],up=0.1)
                    R.E2.VARIABLES.left = '"swiggle(%s,%s,%s)"%(${a},${b},${c})'
                    R.E2.VARIABLES.a="${b}-5"
                    R.E2.VARIABLES.b=5
                    R.E2.VARIABLES.c=100
        """
        # prepare object creation
        kind = "ellipsoid"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object E with E for Ellipsoid
        E = Ellipsoid((self.counter["all"]+1,self.counter[kind]+1),
                      spacefilling=self.isspacefilled, # added on 2023-08-11
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): E.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: E.beadtype = beadtype # bead type (if not defined, default index will apply)
        E.USER.ID = "$"+E.name        # add $ to prevent its execution
        E.USER.args = [x,y,z,a,b,c]   # args = [....] as defined in the class Ellipsoid
        E.USER.beadtype = E.beadtype  # beadtype to be used for create_atoms
        E.USER.side = E.sidearg(side) # extra parameter side
        E.USER.move = E.movearg(move) # move arg
        E.USER.units = E.unitsarg(units) # units
        E.USER.rotate = E.rotatearg(rotate) # rotate
        E.USER.open = E.openarg(open) # open
        # Create the object if not fake
        if fake:
            return E
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = E
            self.nobjects += 1
            return None

    # PLANE method ---------------------------
    # plane args = px py pz nx ny nz
    # px,py,pz = point on the plane (distance units)
    # nx,ny,nz = direction normal to plane (distance units)
    def plane(self,px=0,py=0,pz=0,nx=0,ny=0,nz=1,
                  name=None,beadtype=None,fake=False,
                  side=None,units=None,move=None,rotate=None,open=None,
                  index = None,subindex = None,
                  **variables
                  ):
        """
        creates a plane region
              px,py,pz = point on the plane (distance units)
              nx,ny,nz = direction normal to plane (distance units)

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "plane001"
            beadtype = 1
                fake = False (use True to test the execution)
     index, subindex = object index and subindex

            Extra properties
                side = "in|out"
               units = "lattice|box"
                move = "[${v1} ${v2} ${v3}]" or [v1,v2,v3] as a list
                       with v1,v2,v3 equal-style variables for x,y,z displacement
                       of region over time (distance units)
              rotate = string or 1x7 list (see move) coding for vtheta Px Py Pz Rx Ry Rz
                       vtheta = equal-style variable for rotation of region over time (in radians)
                       Px,Py,Pz = origin for axis of rotation (distance units)
                       Rx,Ry,Rz = axis of rotation vector
                open = integer from 1-6 corresponding to face index

            See examples for elliposid()
        """
        # prepare object creation
        kind = "plane"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object P with P for plane
        P = Plane((self.counter["all"]+1,self.counter[kind]+1),
                      spacefilling=self.isspacefilled, # added on 2023-08-11
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): P.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: P.beadtype = beadtype # bead type (if not defined, default index will apply)
        P.USER.ID = "$"+P.name        # add $ to prevent its execution
        P.USER.args = [px,py,pz,nx,ny,nz]   # args = [....] as defined in the class Plane
        P.USER.beadtype = P.beadtype  # beadtype to be used for create_atoms
        P.USER.side = P.sidearg(side) # extra parameter side
        P.USER.move = P.movearg(move) # move arg
        P.USER.units = P.unitsarg(units) # units
        P.USER.rotate = P.rotatearg(rotate) # rotate
        P.USER.open = P.openarg(open) # open
        # Create the object if not fake
        if fake:
            return P
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = P
            self.nobjects += 1
            return None

    # PRISM method ---------------------------
    # prism args = xlo xhi ylo yhi zlo zhi xy xz yz
    # xlo,xhi,ylo,yhi,zlo,zhi = bounds of untilted prism (distance units)
    # xy = distance to tilt y in x direction (distance units)
    # xz = distance to tilt z in x direction (distance units)
    # yz = distance to tilt z in y direction (distance units)
    def prism(self,xlo=-5,xhi=5,ylo=-5,yhi=5,zlo=-5,zhi=5,xy=1,xz=1,yz=1,
                  name=None,beadtype=None,fake=False,
                  side=None,units=None,move=None,rotate=None,open=None,
                  index = None,subindex = None,
                  **variables
                  ):
        """
        creates a prism region
            xlo,xhi,ylo,yhi,zlo,zhi = bounds of untilted prism (distance units)
            xy = distance to tilt y in x direction (distance units)
            xz = distance to tilt z in x direction (distance units)
            yz = distance to tilt z in y direction (distance units)

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "prism001"
            beadtype = 1
                fake = False (use True to test the execution)
     index, subindex = object index and subindex

            Extra properties
                side = "in|out"
               units = "lattice|box"
                move = "[${v1} ${v2} ${v3}]" or [v1,v2,v3] as a list
                       with v1,v2,v3 equal-style variables for x,y,z displacement
                       of region over time (distance units)
              rotate = string or 1x7 list (see move) coding for vtheta Px Py Pz Rx Ry Rz
                       vtheta = equal-style variable for rotation of region over time (in radians)
                       Px,Py,Pz = origin for axis of rotation (distance units)
                       Rx,Ry,Rz = axis of rotation vector
                open = integer from 1-6 corresponding to face index

            See examples for elliposid()
        """
        # prepare object creation
        kind = "prism"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object P with P for prism
        P = Prism((self.counter["all"]+1,self.counter[kind]+1),
                      spacefilling=self.isspacefilled, # added on 2023-08-11
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): P.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: P.beadtype = beadtype # bead type (if not defined, default index will apply)
        P.USER.ID = "$"+P.name        # add $ to prevent its execution
        P.USER.args = [xlo,xhi,ylo,yhi,zlo,zhi,xy,xz,yz]   # args = [....] as defined in the class Prism
        P.USER.beadtype = P.beadtype  # beadtype to be used for create_atoms
        P.USER.side = P.sidearg(side) # extra parameter side
        P.USER.move = P.movearg(move) # move arg
        P.USER.units = P.unitsarg(units) # units
        P.USER.rotate = P.rotatearg(rotate) # rotate
        P.USER.open = P.openarg(open) # open
        # Create the object if not fake
        if fake:
            return P
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = P
            self.nobjects += 1
            return None

    # SPHERE method ---------------------------
    # sphere args = x y z radius
    # x,y,z = center of sphere (distance units)
    # radius = radius of sphere (distance units)
    # x,y,z, and radius can be a variable (see below)
    def sphere(self,x=0,y=0,z=0,radius=3,
                  name=None,beadtype=None,fake=False,
                  side=None,units=None,move=None,rotate=None,open=None,
                  index = None,subindex = None,
                  **variables
                  ):
        """
        creates a sphere region
              x,y,z = center of sphere (distance units)
              radius = radius of sphere (distance units)
              x,y,z, and radius can be a variable

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "sphere001"
            beadtype = 1
                fake = False (use True to test the execution)
     index, subindex = object index and subindex

            Extra properties
                side = "in|out"
               units = "lattice|box"
                move = "[${v1} ${v2} ${v3}]" or [v1,v2,v3] as a list
                       with v1,v2,v3 equal-style variables for x,y,z displacement
                       of region over time (distance units)
              rotate = string or 1x7 list (see move) coding for vtheta Px Py Pz Rx Ry Rz
                       vtheta = equal-style variable for rotation of region over time (in radians)
                       Px,Py,Pz = origin for axis of rotation (distance units)
                       Rx,Ry,Rz = axis of rotation vector
                open = integer from 1-6 corresponding to face index

            See examples for elliposid()
        """
        # prepare object creation
        kind = "sphere"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object S with S for sphere
        S = Sphere((self.counter["all"]+1,self.counter[kind]+1),
                      spacefilling=self.isspacefilled, # added on 2023-08-11
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): S.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: S.beadtype = beadtype # bead type (if not defined, default index will apply)
        S.USER.ID = "$"+S.name        # add $ to prevent its execution
        S.USER.args = [x,y,z,radius]   # args = [....] as defined in the class Sphere
        S.USER.beadtype = S.beadtype  # beadtype to be used for create_atoms
        S.USER.side = S.sidearg(side) # extra parameter side
        S.USER.move = S.movearg(move) # move arg
        S.USER.units = S.unitsarg(units) # units
        S.USER.rotate = S.rotatearg(rotate) # rotate
        S.USER.open = S.openarg(open) # open
        # Create the object if not fake
        if fake:
            return S
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = S
            self.nobjects += 1
            return None

    # UNION method ---------------------------
    # union args = N reg-ID1 reg-ID2
    def union(self,*regID,
              name=None,beadtype=1,fake=False,
              index = None,subindex = None,
              **variables):
        """
        creates a union region
              union("reg-ID1","reg-ID2",name="myname",beadtype=1,...)
              reg-ID1,reg-ID2, ... = IDs of regions to join together

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "union001"
            beadtype = 1
                fake = False (use True to test the execution)
     index, subindex = object index and subindex
        """
        kind = "union"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object U with U for union
        U = Union((self.counter["all"]+1,self.counter[kind]+1),
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): U.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: U.beadtype = beadtype # bead type (if not defined, default index will apply)
        U.USER.ID = "$"+U.name        # add $ to prevent its execution
        U.USER.side, U.USER.move, U.USER.units, U.USER.rotate, U.USER.open = "","","","",""
        # build arguments based on regID
        nregID = len(regID)
        if nregID<2: raise ValueError('two objects must be given at least for an union')
        args = [None] # the number of arguments is not known yet
        validID = range(nregID)
        for ireg in validID:
            if isinstance(regID[ireg],int):
                if regID[ireg] in validID:
                    args.append(self.names[regID[ireg]])
                else:
                    raise IndexError(f"the index {regID[ireg]} exceeds the number of objects {len(self)}")
            elif isinstance(regID[ireg],str):
                if regID[ireg] in self:
                    args.append(regID[ireg])
                else:
                    raise KeyError(f'the object "{regID[ireg]}" does not exist')
            else:
                raise KeyError(f"the {ireg+1}th object should be given as a string or an index")
            # prevent the creation of atoms merged (avoid duplicates)
            self.objects[regID[ireg]].FLAGSECTIONS["create"] = False
        args[0] = len(regID)
        U.USER.args = args   # args = [....] as defined in the class Union
        # Create the object if not fake
        if fake:
            return U
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = U
            self.nobjects += 1
            return None

    # UNION method ---------------------------
    # union args = N reg-ID1 reg-ID2
    def intersect(self,*regID,
              name=None,beadtype=1,fake=False,
              index = None,subindex = None,
              **variables):
        """
        creates an intersection region
              intersect("reg-ID1","reg-ID2",name="myname",beadtype=1,...)
              reg-ID1,reg-ID2, ... = IDs of regions to join together

            URL: https://docs.lammps.org/region.html

            Main properties = default value
                name = "intersect001"
            beadtype = 1
                fake = False (use True to test the execution)
     index, subindex = object index and subindex
        """
        kind = "intersect"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object I with I for intersect
        I = Intersect((self.counter["all"]+1,self.counter[kind]+1),
                      index=index,subindex=subindex,**variables)
        # feed USER fields
        if name not in (None,""): I.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: I.beadtype = beadtype # bead type (if not defined, default index will apply)
        I.USER.ID = "$"+I.name        # add $ to prevent its execution
        I.USER.side, I.USER.move, I.USER.units, I.USER.rotate, I.USER.open = "","","","",""
        # build arguments based on regID
        nregID = len(regID)
        if nregID<2: raise ValueError('two objects must be given at least for an intersection')
        args = [None] # the number of arguments is not known yet
        validID = range(nregID)
        for ireg in validID:
            if isinstance(regID[ireg],int):
                if regID[ireg] in validID:
                    args.append(self.names[regID[ireg]])
                else:
                    raise IndexError(f"the index {regID[ireg]} exceeds the number of objects {len(self)}")
            elif isinstance(regID[ireg],str):
                if regID[ireg] in self:
                    args.append(regID[ireg])
                else:
                    raise KeyError(f'the object "{regID[ireg]}" does not exist')
            else:
                raise KeyError(f"the {ireg+1}th object should be given as a string or an index")
            # prevent the creation of atoms (avoid duplicates)
            self.objects[regID[ireg]].FLAGSECTIONS["create"] = False
        args[0] = len(regID)
        I.USER.args = args   # args = [....] as defined in the class Union
        # Create the object if not fake
        if fake:
            return I
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = I
            self.nobjects += 1
            return None


    # Group method ---------------------------
    def group(self,obj,name=None,fake=False):
        pass


    # COLLECTION method ---------------------------
    def collection(self,*obj,name=None,beadtype=None,fake=False,
              index = None,subindex = None,
              **kwobj):
        kind = "collection"
        if index is None: index = self.counter["all"]+1
        if subindex is None: subindex = self.counter[kind]+1
        # create the object C with C for collection
        C = Collection((index,subindex))
        if name not in (None,""): C.name = name # object name (if not defined, default name will be used)
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        if beadtype is not None: C.beadtype = beadtype # bead type (if not defined, default index will apply)
        # add objects
        C.collection = regioncollection(*obj,**kwobj)
        # apply modifications (beadtype, ismask)
        for o in C.collection.keys():
            tmp = C.collection.getattr(o)
            if beadtype != None: tmp.beadtype = beadtype
            C.collection.setattr(o,tmp)
        # Create the object if not fake
        if fake:
            return C
        else:
            self.counter["all"] += 1
            self.counter[kind] +=1
            self.objects[name] = C
            self.nobjects += 1
            return None

    def scatter(self,
                 E,
                 name="emulsion",
                 beadtype=None,
                 ):
        """


        Parameters
        ----------
        E : scatter or emulsion object
            codes for x,y,z and r.
        name : string, optional
            name of the collection. The default is "emulsion".
        beadtype : integer, optional
            for all objects. The default is 1.

        Raises
        ------
        TypeError
            Return an error of the object is not a scatter type.

        Returns
        -------
        None.

        """
        if isinstance(E,scatter):
            collect = {}
            for i in range(E.n):
                b = E.beadtype[i] if beadtype==None else beadtype
                nameobj = "glob%02d" % i
                collect[nameobj] = self.sphere(E.x[i],E.y[i],E.z[i],E.r[i],
                            name=nameobj,beadtype=b,fake=True)
            self.collection(**collect,name=name)
        else:
            raise TypeError("the first argument must be an emulsion object")



    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
    #
    # LOW-LEVEL METHODS
    #
    #
    # Low-level methods to manipulate and operate region objects (e.g., R).
    # They implement essentially some Python standards with the following
    # shortcut: R[i] or R[objecti] and R.objecti and R.objects[objecti] are
    # the same ith object where R.objects is the original container
    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-

    # repr() method ----------------------------
    def __repr__(self):
        """ display method """
        spacefillingstr = f"\n(space filled with beads of type {self.spacefillingbeadtype})" \
            if self.isspacefilled else ""
        print("-"*40)
        print('REGION container "%s" with %d objects %s' % (self.name,self.nobjects,spacefillingstr))
        if self.nobjects>0:
            names = self.names
            l = [len(n) for n in names]
            width = max(10,max(l)+2)
            fmt = "%%%ss:" % width
            for i in range(self.nobjects):
                flags = "("+self.objects[names[i]].shortflags+")" if self.objects[names[i]].flags else "(no script)"
                if isinstance(self.objects[names[i]],Collection):
                        print(fmt % names[i]," %s region (%d beadtypes)" % \
                              (self.objects[names[i]].kind,len(self.objects[names[i]].beadtype))," > ",flags)
                else:
                    print(fmt % names[i]," %s region (beadtype=%d)" % \
                          (self.objects[names[i]].kind,self.objects[names[i]].beadtype)," > ",flags)
            print(wrap("they are",":",", ".join(self.names),10,60,80))
        print("-"*40)
        return "REGION container %s with %d objects (%s)" % \
            (self.name,self.nobjects,",".join(self.names))

    # str() method ----------------------------
    def __str__(self):
        """ string representation of a region """
        return "REGION container %s with %d objects (%s)" % \
            (self.name,self.nobjects,",".join(self.names))

    # generic GET method ----------------------------
    def get(self,name):
        """ returns the object """
        if name in self.objects:
            return self.objects[name]
        else:
            raise NameError('the object "%s" does not exist, use list()' % name)

    # getattr() method ----------------------------
    def __getattr__(self,name):
        """ getattr attribute override """
        if (name in self.__dict__) or (name in protectedregionkeys):
            return self.__dict__[name] # higher precedence for root attributes
        elif name in protectedregionkeys:
            return getattr(type(self), name).__get__(self) # for methods decorated as properties (@property)
        else:
            return self.get(name)

    # generic SET method ----------------------------
    def set(self,name,value):
        """ set field and value """
        if isinstance(value,list) and len(value)==0:
            if name not in self.objects:
                raise NameError('the object "%s" does not exist, use list()' % name)
            self.delete(name)
        elif isinstance(value,coregeometry):
            if name in self.objects: self.delete(name)
            if isinstance(value.SECTIONS,pipescript) or isinstance(value,Evalgeometry):
                self.eval(deepduplicate(value),name) # not a scalar
            else: # scalar
                self.objects[name] = deepduplicate(value)
                self.objects[name].name = name
                self.nobjects += 1
                self.counter["all"] += 1
                self.objects[name].index = self.counter["all"]
                self.counter[value.kind] += 1

    # setattr() method ----------------------------
    def __setattr__(self,name,value):
        """ setattr override """
        if name in protectedregionkeys: # do not forget to increment protectedregionkeys
            self.__dict__[name] = value # if not, you may enter in infinite loops
        else:
            self.set(name,value)

    # generic HASATTR method ----------------------------
    def hasattr(self,name):
        """ return true if the object exist """
        if not isinstance(name,str): raise TypeError("please provide a string")
        return name in self.objects

    # IN operator ----------------------------
    def __contains__(self,obj):
        """ in override """
        return self.hasattr(obj)

    # len() method ----------------------------
    def __len__(self):
        """ len method """
        return len(self.objects)

    # indexing [int] and ["str"] method ----------------------------
    def __getitem__(self,idx):
        """
            R[i] returns the ith element of the structure
            R[:4] returns a structure with the four first fields
            R[[1,3]] returns the second and fourth elements
        """
        if isinstance(idx,int):
            if idx<len(self):
                return self.get(self.names[idx])
            raise IndexError(f"the index should be comprised between 0 and {len(self)-1}")
        elif isinstance(idx,str):
            if idx in self:
                return self.get(idx)
            raise NameError(f'{idx} does not exist, use list() to list objects')
        elif isinstance(idx,list):
            pass
        elif isinstance(idx,slice):
            return self.__getitem__(self,list(range(*idx.indices(len(self)))))
        else:
            raise IndexError("not implemented yet")

    # duplication GET method based on DICT ----------------------------
    def __getstate__(self):
        """ getstate for cooperative inheritance / duplication """
        return self.__dict__.copy()

    # duplication SET method based on DICT ----------------------------
    def __setstate__(self,state):
        """ setstate for cooperative inheritance / duplication """
        self.__dict__.update(state)

    # iterator method ----------------------------
    def __iter__(self):
        """ region iterator """
        # note that in the original object _iter_ is a static property not in dup
        dup = duplicate(self)
        dup._iter_ = 0
        return dup

    # next iterator method ----------------------------
    def __next__(self):
        """ region iterator """
        self._iter_ += 1
        if self._iter_<=len(self):
            return self[self._iter_-1]
        self._iter_ = 0
        raise StopIteration(f"Maximum region.objects iteration reached {len(self)}")


    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
    #
    # MIDDLE-LEVEL METHODS
    #
    #
    # These methods are specific to PIZZA.REGION() objects.
    # They bring useful methods for the user and developer.
    # Similar methods exist in PIZZA.RASTER()
    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-

    # LIST method ----------------------------
    def list(self):
        """ list objects """
        fmt = "%%%ss:" % max(10,max([len(n) for n in self.names])+2)
        print('REGION container "%s" with %d objects' % (self.name,self.nobjects))
        for o in self.objects.keys():
            print(fmt % self.objects[o].name,"%-10s" % self.objects[o].kind,
                  "(beadtype=%d,object index=[%d,%d])" % \
                      (self.objects[o].beadtype,
                       self.objects[o].index,
                       self.objects[o].subindex))

    # NAMES method set as an attribute ----------------------------
    @property
    def names(self):
        """ return the names of objects sorted as index """
        namesunsorted=namessorted=list(self.objects.keys())
        nobj = len(namesunsorted)
        if nobj<1:
            return []
        elif nobj<2:
            return namessorted
        else:
            for iobj in range(nobj):
                namessorted[self.objects[namesunsorted[iobj]].index-1] = namesunsorted[iobj]
            return namessorted

    # NBEADS method set as an attribute
    @property
    def nbeads(self):
        "return the number of beadtypes used"
        if len(self)>0:
            guess = max(len(self.count()),self.live.nbeads)
            return guess+1 if self.isspacefilled else guess
        else:
            return self.live.nbeads

    # COUNT method
    def count(self):
        """ count objects by type """
        typlist = []
        for  o in self.names:
            if isinstance(self.objects[o].beadtype,list):
                typlist += self.objects[o].beadtype
            else:
                typlist.append(self.objects[o].beadtype)
        utypes = list(set(typlist))
        c = []
        for t in utypes:
            c.append((t,typlist.count(t)))
        return c

    # DELETE method
    def delete(self,name):
        """ delete object """
        if name in self.objects:
            kind = self.objects[name].kind
            del self.objects[name]
            self.nobjects -= 1
            self.counter[kind] -= 1
            self.counter["all"] -= 1
        else:
            raise NameError("%s does not exist (use list()) to list valid objects" % name)

    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
    #
    # HIGH-LEVEL METHODS
    #
    #
    # These methods are connect PIZZA.REGION() objects with their equivalent
    # as PIZZA.SCRIPT() and PIZZA.PIPESCRIPT() objects and methods.
    #
    # They are essential to PIZZA.REGION(). They do not have equivalent in
    # PIZZA.RASTER(). They use extensively the methods attached to :
    #        PIZZA.REGION.LAMMPSGENERIC()
    #        PIZZA.REGION.COREGEOMETRY()
    #
    # Current real-time rendering relies on
    #   https://andeplane.github.io/atomify/
    # which gives better results than
    #   https://editor.lammps.org/
    # +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-

    # EVALUATE algebraic operation on PIZZA.REGION() objects (operation on codes)
    def eval(self,expression,name=None,beadtype = None,
             fake=False,index = None,subindex = None):
        """
            evaluates (i.e, combine scripts) an expression combining objects
                R= region(name="my region")
                R.eval(o1+o2+...,name='obj')
                R.eval(o1|o2|...,name='obj')
            R.name will be the resulting object of class region.eval (region.coregeometry)
        """
        if not isinstance(expression, coregeometry): raise TypeError("the argument should be a region.coregeometry")
        # prepare object creation
        kind = "eval"
        self.counter["all"] += 1
        self.counter[kind] +=1
        if index is None: index = self.counter["all"]
        if subindex is None: subindex = self.counter[kind]
        # create the object E with E for Ellipsoid
        E = Evalgeometry((self.counter["all"],self.counter[kind]),
                      index=index,subindex=subindex)
        # link expression to E
        if beadtype is not None: E.beadtype = beadtype # bead type (if not defined, default index will apply)
        if name is None: name = expression.name
        if name in self.name: raise NameError('the name "%s" is already used' % name)
        E.name = name
        E.SECTIONS = expression.SECTIONS
        E.USER = expression.USER
        if isinstance(E.SECTIONS,pipescript):
            # set beadtypes for all sections and scripts in the pipeline
            for i in E.SECTIONS.keys():
                for j in range(len(E.SECTIONS[i])):
                    E.SECTIONS[i].USER[j].beadtype = E.beadtype
        E.USER.beadtype = beadtype
        # Create the object if not fake
        if fake:
            self.counter["all"] -= 1
            self.counter[kind] -= 1
            return E
        else:
            self.objects[name] = E
            self.nobjects += 1
            return None

    # PIPESCRIPT method generates a pipe for all objects and sections
    def pipescript(self):
        """ pipescript all objects in the region """
        if len(self)<1: return pipescript()
        # execute all objects
        for myobj in self:
            if not isinstance(myobj,Collection): myobj.do()
        # concatenate all objects into a pipe script
        # for collections, only group is accepted
        liste = [x.SECTIONS["variables"] for x in self if not isinstance(x,Collection) and x.hasvariables] + \
                [x.SECTIONS["region"]    for x in self if not isinstance(x,Collection) and x.hasregion] + \
                [x.SECTIONS["create"]    for x in self if not isinstance(x,Collection) and x.hascreate] + \
                [x.SECTIONS["group"]     for x in self if not isinstance(x,Collection) and x.hasgroup] + \
                [x.SECTIONS["setgroup"]  for x in self if not isinstance(x,Collection) and x.hassetgroup] + \
                [x.SECTIONS["move"]      for x in self if not isinstance(x,Collection) and x.hasmove]
        # add the objects within the collection
        for x in self:
            if isinstance(x,Collection): liste += x.group()
        # add the eventual group for the collection
        liste += [x.SECTIONS["group"] for x in self if isinstance(x,Collection) and x.hasgroup]
        # chain all scripts
        return pipescript.join(liste)

    # SCRIPT add header and foodter to PIPECRIPT
    def script(self,live=False):
        """ script all objects in the region """
        s = self.pipescript().script()
        if self.isspacefilled:
            USERspacefilling =regiondata(**self.spacefilling)
            s = LammpsSpacefilling(**USERspacefilling)+s
        if live:
            beadtypes = [ x[0] for x in self.count() ]
            USER = regiondata(**self.live)
            USER.nbeads = self.nbeads
            USER.mass = "$"
            USER.pair_coeff = "$"
            # list beadtype and prepare  mass, pair_coeff
            beadtypes = [ x[0] for x in self.count() ]
            if self.isspacefilled and self.spacefillingbeadtype not in beadtypes:
                beadtypes = [self.spacefillingbeadtype]+beadtypes
            for b in beadtypes:
                USER.mass += livetemplate["mass"] % b +"\n"
                USER.pair_coeff += livetemplate["pair_coeff"] %(b,b) +"\n"
            for b1 in beadtypes:
                for b2 in beadtypes:
                    if b2>b1:
                        USER.pair_coeff += livetemplate["pair_coeff"] %(b1,b2) +"\n"
            livemode = "dynamic" if self.hasfixmove else "static"
            USER.run =self.livelammps["options"][livemode]["run"]
            s = LammpsHeader(**USER)+s+LammpsFooter(**USER)
        return s

    # DO METHOD = main static compiler
    def do(self):
        """ execute the entire script """
        return self.pipescript().do()

    # DOLIVE = fast code generation for online rendering
    def dolive(self):
        """
            execute the entire script for online testing
            see: https://editor.lammps.org/
        """
        self.livelammps["file"] = self.script(live=True).tmpwrite()
        if not self.livelammps["active"]:
            livelammps(self.livelammps["URL"],new=0)
            self.livelammps["active"] = True
        return self.livelammps["file"]

# %% scatter class and emulsion class
#    Simplified scatter and emulsion generator
#    generalized from its 2D version in raster.scatter and raster.emulsion
#    added on 2023-03-10

class scatter():
    """ generic top scatter class """
    def __init__(self):
        """
        The scatter class provides an easy constructor
        to distribute in space objects according to their
        positions x,y,z size r (radius) and beadtype.

        The class is used to derive emulsions.

        Returns
        -------
        None.
        """
        self.x = np.array([],dtype=int)
        self.y = np.array([],dtype=int)
        self.z = np.array([],dtype=int)
        self.r = np.array([],dtype=int)
        self.beadtype = []

    @property
    def n(self):
        return len(self.x)

    def pairdist(self,x,y,z):
        """ pair distance to the surface of all disks/spheres """
        if self.n==0:
            return np.Inf
        else:
            return np.sqrt((x-self.x)**2+(y-self.y)**2+(z-self.z)**2)-self.r


class emulsion(scatter):
    """ emulsion generator """

    def __init__(self, xmin=10, ymin=10, zmin=10, xmax=90, ymax=90, zmax=90,
                 maxtrials=1000, beadtype=1, forcedinsertion=True):
        """


        Parameters
        ----------
        The insertions are performed between xmin,ymin and xmax,ymax
        xmin : int64 or real, optional
            x left corner. The default is 10.
        ymin : int64 or real, optional
            y bottom corner. The default is 10.
        zmin : int64 or real, optional
            z bottom corner. The default is 10.
        xmax : int64 or real, optional
            x right corner. The default is 90.
        ymax : int64 or real, optional
            y top corner. The default is 90.
        zmax : int64 or real, optional
            z top corner. The default is 90.
        beadtype : default beadtype to apply if not precised at insertion
        maxtrials : integer, optional
            Maximum of attempts for an object. The default is 1000.
        forcedinsertion : logical, optional
            Set it to true to force the next insertion. The default is True.

        Returns
        -------
        None.

        """
        super().__init__()
        self.xmin, self.xmax, self.ymin, self.ymax, self.zmin, self.zmax = xmin, xmax, ymin, ymax, zmin, zmax
        self.lastinsertion = (None,None,None,None,None) # x,y,z,r, beadtype
        self.length = xmax-xmin
        self.width = ymax-ymin
        self.height = zmax-zmin
        self.defautbeadtype = beadtype
        self.maxtrials = maxtrials
        self.forcedinsertion = forcedinsertion

    def __repr__(self):
        print(f" Emulsion object\n\t{self.length}x{self.width}x{self.height} starting at x={self.xmin}, y={self.ymin}, z={self.zmin}")
        print(f"\tcontains {self.n} insertions")
        print("\tmaximum insertion trials:", self.maxtrials)
        print("\tforce next insertion if previous fails:", self.forcedinsertion)
        return f"emulsion with {self.n} insertions"


    def walldist(self,x,y,z):
        """ shortest distance to the wall """
        return min(abs(x-self.xmin),abs(y-self.ymin),abs(z-self.zmin),abs(x-self.xmax),abs(y-self.ymax),abs(z-self.zmax))

    def dist(self,x,y,z):
        """ shortest distance of the center (x,y) to the wall or any object"""
        return np.minimum(np.min(self.pairdist(x,y,z)),self.walldist(x,y,z))

    def accepted(self,x,y,z,r):
        """ acceptation criterion """
        return self.dist(x,y,z)>r

    def rand(self):
        """ random position x,y  """
        return  np.random.uniform(low=self.xmin,high=self.xmax), \
                np.random.uniform(low=self.ymin,high=self.ymax),\
                np.random.uniform(low=self.zmin,high=self.zmax)

    def setbeadtype(self,beadtype):
        """ set the default or the supplied beadtype  """
        if beadtype == None:
            self.beadtype.append(self.defautbeadtype)
            return self.defautbeadtype
        else:
            self.beadtype.append(beadtype)
            return beadtype

    def insertone(self,x=None,y=None,z=None,r=None,beadtype=None,overlap=False):
        """
            insert one object of radius r
            properties:
                x,y,z coordinates (if missing, picked randomly from uniform distribution)
                r radius (default = 2% of diagonal)
                beadtype (default = defautbeadtype)
                overlap = False (accept only if no overlap)
        """
        attempt, success = 0, False
        random = (x==None) or (y==None) or (z==None)
        if r==None:
            r = 0.02*np.sqrt(self.length**2+self.width**2+self.height**2)
        while not success and attempt<self.maxtrials:
            attempt += 1
            if random: x,y,z = self.rand()
            if overlap:
                success = True
            else:
                success = self.accepted(x,y,z,r)
        if success:
            self.x = np.append(self.x,x)
            self.y = np.append(self.y,y)
            self.z = np.append(self.z,z)
            self.r = np.append(self.r,r)
            b=self.setbeadtype(beadtype)
            self.lastinsertion = (x,y,z,r,b)
        return success

    def insertion(self,rlist,beadtype=None):
        """
            insert a list of objects
                nsuccess=insertion(rlist,beadtype=None)
                beadtype=b forces the value b
                if None, defaultbeadtype is used instead
        """
        rlist.sort(reverse=True)
        ntodo = len(rlist)
        n = nsuccess = 0
        stop = False
        while not stop:
            n += 1
            success = self.insertone(r=rlist[n-1],beadtype=beadtype)
            if success: nsuccess += 1
            stop = (n==ntodo) or (not success and not self.forcedinsertion)
        if nsuccess==ntodo:
            print(f"{nsuccess} objects inserted successfully")
        else:
            print(f"partial success: {nsuccess} of {ntodo} objects inserted")
        return nsuccess



# %% debug section - generic code to test methods (press F5)
# ===================================================
# main()
# ===================================================
# for debugging purposes (code called as a script)
# the code is called from here
# ===================================================
if __name__ == '__main__':
    # early example
    a=region(name="region A")
    b=region(name="region B")
    c = [a,b]
    # step 1
    R = region(name="my region")
    R.ellipsoid(0, 0, 0, 1, 1, 1,name="E1",toto=3)
    R
    repr(R.E1)
    R.E1.VARIABLES.a=1
    R.E1.VARIABLES.b=2
    R.E1.VARIABLES.c="(${a},${b},100)"
    R.E1.VARIABLES.d = '"%s%s" %("test",${c}) # note that test could be replaced by any function'
    R.E1
    code1 = R.E1.do()
    print(code1)
    # step 2
    R.ellipsoid(0,0,0,1,1,1,name="E2",side="out",move=["left","${up}*3",None],up=0.1)
    R.E2.VARIABLES.left = '"swiggle(%s,%s,%s)"%(${a},${b},${c})'
    R.E2.VARIABLES.a="${b}-5"
    R.E2.VARIABLES.b=5
    R.E2.VARIABLES.c=100
    code2 = R.E2.do()
    print(R)
    repr(R.E2)
    print(code2)
    print(R.names)
    R.list()

    # eval objects
    R.set('E3',R.E2)
    R.E3.beadtype = 2
    R.set('add',R.E1 + R.E2)
    R.addd2 = R.E1 + R.E2
    R.eval(R.E1 | R.E2,'E12')


    # How to manage pipelines
    print("\n","-"*20,"pipeline","-"*20)
    p = R.E2.script
    s = p.script() # first execution
    s = p.script() # do nothing
    s # check

    # reorganize scripts
    print("\n","-"*20,"change order","-"*20)
    p.clear() # undo executions first
    q = p[[0,2,1]]
    sq = q.script()
    print(q.do())

    # join sections
    liste = [x.SECTIONS["variables"] for x in R]
    pliste = pipescript.join(liste)


    # Example closer to production
    P = region(name="live test",width = 20)
    P.ellipsoid(0, 0, 0, "${Ra}", "${Rb}", "${Rc}",
              name="E1", Ra=5,Rb=2,Rc=3)
    P.sphere(7,0,0,radius="${R}",name = "S1", R=2)
    cmd = P.do()
    print(cmd)
    #outputfile = P.dolive()

    # EXAMPLE: gel compression
    name = ['top','food','tongue','bottom']
    scale = 3 # tested up to scale = 10 to reach million of beads
    radius = [10,5,8,10]
    height = [1,4,3,1]
    spacer = 2 * scale
    radius = [r*scale for r in radius]
    height = [h*scale for h in height]
    position_original = [spacer+height[1]+height[2]+height[3],
                          height[2]+height[3],
                          height[3],
                          0]
    beadtype = [1,2,3,1]
    total_height = sum(height) +spacer
    position = [x-total_height/2 for x in position_original]
    B = region(name = 'region container',
                width=2*max(radius),
                height=total_height,
                depth=2*max(radius))
    for i in range(len(name)):
        B.cylinder(name = name[i],
                    c1=0,
                    c2=0,
                    radius=radius[i],
                    lo=position[i],
                    hi=position[i]+height[i],
                    beadtype=beadtype[i])
    B.dolive()


    # emulsion example
    mag = 3
    e = emulsion(xmin=-5*mag, ymin=-5*mag, zmin=-5*mag,xmax=5*mag, ymax=5*mag, zmax=5*mag)
    e.insertion([2,2,2,1,1.6,1.2,1.4,1.3],beadtype=3)
    e.insertion([0.6,0.3,2,1.5,1.5,1,2,1.2,1.1,1.3],beadtype=1)
    e.insertion([3,1,2,2,4,1,1.2,2,2.5,1.2,1.4,1.6,1.7],beadtype=2)
    e.insertion([3,1,2,2,4,1,5.2,2,4.5,1.2,1.4,1.6,1.7],beadtype=4)

    # b = region()
    # a = region()
    # a.sphere(1,1,1,1,name='sphere1')
    # a.sphere(1,2,2,1,name='sphere2')
    # b.collection(a, name='acollection')

    C = region(name='cregion',width=11*mag,height=11*mag,depth=11*mag)
    C.scatter(e)
    C.script()
    g = C.emulsion.group()
    C.dolive()
