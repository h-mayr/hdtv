# -*- coding: utf-8 -*-

# HDTV - A ROOT-based spectrum analysis software
#  Copyright (C) 2006-2009  The HDTV development team (see file AUTHORS)
#
# This file is part of HDTV.
#
# HDTV is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# HDTV is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDTV; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA
import ROOT
import hdtv.cmdline
import hdtv.options
import hdtv.util
import hdtv.ui
import hdtv.fit

import copy
import sys


class FitInterface(object):
    """
    User interface for fitting 1-d spectra
    """

    def __init__(self, spectra):
        hdtv.ui.debug("Loaded user interface for fitting of 1-d spectra")

        self.spectra = spectra
        self.window = self.spectra.window

        # tv commands
        self.tv = TvFitInterface(self)

        # Register configuration variables for fit interface
        # default region width for quickfit

        self.opt = dict()
        self.opt['quickfit.region'] = hdtv.options.Option(
            default=20.0, parse=lambda x: float(x))
        hdtv.options.RegisterOption(
            "fit.quickfit.region", self.opt['quickfit.region'])

        self.opt['display.decomp'] = hdtv.options.Option(
            default=False,
            parse=hdtv.options.ParseBool,
            changeCallback=lambda x: self.SetDecomposition(x))
        hdtv.options.RegisterOption(
            "fit.display.decomp", self.opt['display.decomp'])

        # Register hotkeys
        self.window.AddHotkey(ROOT.kKey_b,
                              lambda: self.spectra.SetMarker("bg"))
        self.window.AddHotkey([ROOT.kKey_Minus, ROOT.kKey_b],
                              lambda: self.spectra.RemoveMarker("bg"))
        self.window.AddHotkey(ROOT.kKey_r,
                              lambda: self.spectra.SetMarker("region"))
        self.window.AddHotkey([ROOT.kKey_Minus, ROOT.kKey_r],
                              lambda: self.spectra.RemoveMarker("region"))
        self.window.AddHotkey(ROOT.kKey_p,
                              lambda: self.spectra.SetMarker("peak"))
        self.window.AddHotkey([ROOT.kKey_Minus, ROOT.kKey_p],
                              lambda: self.spectra.RemoveMarker("peak"))
        self.window.AddHotkey(ROOT.kKey_B,
                              lambda: self.spectra.ExecuteFit(peaks=False))
        self.window.AddHotkey(ROOT.kKey_F,
                              lambda: self.spectra.ExecuteFit(peaks=True))
        self.window.AddHotkey([ROOT.kKey_Minus, ROOT.kKey_B],
                              lambda: self.spectra.ClearFit(bg_only=True))
        self.window.AddHotkey([ROOT.kKey_Minus, ROOT.kKey_F],
                              lambda: self.spectra.ClearFit(bg_only=False))
        self.window.AddHotkey(ROOT.kKey_Q, self.QuickFit)
        self.window.AddHotkey(
            [ROOT.kKey_Plus, ROOT.kKey_F], self.spectra.StoreFit)
        self.window.AddHotkey(
            [ROOT.kKey_Minus, ROOT.kKey_F], self.spectra.ClearFit)
        self.window.AddHotkey(ROOT.kKey_D,
                              lambda: self.ShowDecomposition(True))
        self.window.AddHotkey([ROOT.kKey_Minus, ROOT.kKey_D],
                              lambda: self.ShowDecomposition(False))

        self.window.AddHotkey([ROOT.kKey_f, ROOT.kKey_s],
                              lambda: self.window.EnterEditMode(prompt="Show Fit: ",
                                                                handler=self._HotkeyShow))
        self.window.AddHotkey([ROOT.kKey_f, ROOT.kKey_a], lambda: self.window.EnterEditMode(
            prompt="Activate Fit: ", handler=self._HotkeyActivate))
        self.window.AddHotkey([ROOT.kKey_f, ROOT.kKey_p],
                              lambda: self._HotkeyShow("PREV"))
        self.window.AddHotkey([ROOT.kKey_f, ROOT.kKey_n],
                              lambda: self._HotkeyShow("NEXT"))

        self.window.AddHotkey(ROOT.kKey_I, self.spectra.ExecuteIntegral)

    def _HotkeyShow(self, args):
        """
        Show wrapper for use with a Hotkey (internal use)
        """
        spec = self.spectra.GetActiveObject()
        if spec is None:
            self.window.viewport.SetStatusText("No active spectrum")
            return
        try:
            ids = hdtv.util.ID.ParseIds(args, spec)
        except ValueError:
            self.window.viewport.SetStatusText(
                "Invalid fit identifier: %s" % args)
            return
        spec.ShowObjects(ids)

    def _HotkeyActivate(self, args):
        """
        ActivateObject wrapper for use with a Hotkey (internal use)
        """
        spec = self.spectra.GetActiveObject()
        if spec is None:
            self.window.viewport.SetStatusText("No active spectrum")
            return
        try:
            ids = hdtv.util.ID.ParseIds(args, spec)
        except ValueError:
            self.window.viewport.SetStatusText(
                "Invalid fit identifier: %s" % args)
            return
        if len(ids) == 1:
            self.window.viewport.SetStatusText("Activating fit %s" % ids[0])
            self.spectra.ActivateFit(ids[0])
        elif len(ids) == 0:
            self.window.viewport.SetStatusText("Deactivating fit")
            self.spectra.ActivateFit(None)
        else:
            self.window.viewport.SetStatusText("Can only activate one fit")

    def ExecuteRefit(self, specID, fitID, peaks=True):
        """
        Re-Execute Fit on store fits
        """
        try:
            spec = self.spectra.dict[specID]
        except KeyError:
            raise KeyError("invalid spectrum ID")
        try:
            fit = spec.dict[fitID]
        except KeyError:
            raise KeyError("invalid fit ID")
        if peaks:
            fit.FitPeakFunc(spec)
        else:
            if fit.fitter.bgdeg == -1:
                raise RuntimeError("background degree of -1")
            fit.FitBgFunc(spec)
        hdtv.ui.msg(str(fit))
        fit.Draw(self.window.viewport)

    def QuickFit(self, pos=None):
        """
        Set region and peak markers automatically and do a quick fit as position "pos".

        If pos is not given, use cursor position
        """
        if pos is None:
            pos = self.window.viewport.GetCursorX()
        self.spectra.ClearFit()
        region_width = hdtv.options.Get("fit.quickfit.region")
        self.spectra.SetMarker("region", pos - region_width / 2.)
        self.spectra.SetMarker("region", pos + region_width / 2.)
        self.spectra.SetMarker("peak", pos)
        self.spectra.ExecuteFit()

    def ListFits(self, sid=None, ids=None, sortBy=None, reverseSort=False):
        """
        List results of stored fits as nice table
        """
        if sid is None:
            sid = self.spectra.activeID
        spec = self.spectra.dict[sid]
        # if there are not fits for this spectrum, there is not much to do
        if len(spec.ids) == 0:
            hdtv.ui.newline()
            hdtv.ui.msg("Spectrum " + str(sid) +
                        " (" + spec.name + "): No fits")
            hdtv.ui.newline()
            return
        # create result header
        result_header = "Fits in Spectrum " + \
            str(sid) + " (" + spec.name + ")" + "\n"
        if ids is None:
            ids = spec.ids
        fits = [spec.dict[ID] for ID in ids]
        count_fits = len(fits)
        (objects, params) = self.ExtractFits(fits)

        # create result footer
        result_footer = "\n" + str(len(objects)) + \
            " peaks in " + str(count_fits) + " fits."
        # create the table
        try:
            table = hdtv.util.Table(
                objects,
                params,
                sortBy=sortBy,
                reverseSort=reverseSort,
                extra_header=result_header,
                extra_footer=result_footer)
            hdtv.ui.msg(str(table))
        except KeyError as e:
            raise hdtv.cmdline.HDTVCommandError(
                "Spectrum " + str(sid) + ": No such attribute: " + str(e) + '\n'
                "Spectrum " + str(sid) + ": Valid attributes are: " + str(params))

    def PrintWorkFit(self):
        """
        Print results of workFit as nice table
        """
        fit = self.spectra.workFit
        if fit.spec is not None:
            hdtv.ui.msg(str(fit))

    def ExtractFits(self, fits):
        """
        Helper function for use with ListFits and PrintWorkFit functions.

        Return values:
            fitlist    : a list of dicts for each peak in the fits
            params     : a ordered list of valid parameter names
        """
        fitlist = list()
        params = list()
        # loop through fits
        for fit in fits:
            # Get peaks
            (peaklist, fitparams) = fit.ExtractParams()
            if len(peaklist) == 0:
                continue
            # update list of valid params
            for p in fitparams:
                # do not use set operations here to keep order of params
                if p not in params:
                    params.append(p)
            # add peaks to the list
            fitlist.extend(peaklist)
        return (fitlist, params)

    def ShowFitterStatus(self, ids=None):
        """
        Show status of the fit parameters of the work Fit.

        If default is true, the status of the default Fitter is shown in addition.
        If a list of ids is given, the status of the fitters belonging to that
        fits is also shown. Note, that the latter will silently fail for invalid
        IDs.
        """
        if ids is None:
            ids = list()
        ids.extend("a")
        statstr = str()
        for ID in ids:
            if ID == "a":
                fitter = self.spectra.workFit.fitter
                statstr += "active fitter: \n"
            else:
                spec = self.spectra.GetActiveObject()
                if spec is None:
                    continue
                fitter = spec.dict[ID].fitter
                statstr += "fitter status of fit id %d: \n" % ID
            statstr += "Background model: polynomial, deg=%d\n" % fitter.bgdeg
            statstr += "Peak model: %s\n" % fitter.peakModel.name
            statstr += "\n"
            statstr += fitter.OptionsStr()
            statstr += "\n\n"
        hdtv.ui.msg(statstr)

    def SetFitterParameter(self, parname, status, ids=None):
        """
        Sets status of fitter parameter

        If not specified otherwise only the fitter of the workFit will be changed.
        If a list of fits is given, we try to set the parameter status also
        for these fits. Be aware that failures for the fits from the list will
        be silently ignored.
        """
        # active fit
        fit = self.spectra.workFit
        status = status.split(",")  # Create list from multiple stati
        if len(status) == 1:
            # Only single status was given so SetParameter need single string
            status = status[0]
        try:
            fit.fitter.SetParameter(parname, status)
            fit.Refresh()
        except ValueError as msg:
            hdtv.ui.error("while editing active Fit: \n\t%s" % msg)
        # fit list
        if not ids:   # works for None and empty list
            return
        spec = self.spectra.GetActiveObject()
        if spec is None:
            hdtv.ui.warn("No active spectrum")
        try:
            iter(ids)
        except TypeError:
            ids = [ids]
        for ID in ids:
            try:
                fit = spec.dict[ID]
                fit.fitter.SetParameter(parname, status)
                fit.Refresh()
            except KeyError:
                pass

    def ResetFitterParameters(self, ids=None):
        """
        Reset Status of Fitter

        The fitter of the workFit is resetted to the internal default values .
        If a list with ids is given, they are treated in the same way as the workFit.
        """
        # active Fit
        fit = self.spectra.workFit
        fit.fitter.ResetParamStatus()
        fit.Refresh()
        # fit list
        if not ids:  # works for None and empty list
            return
        spec = self.spectra.GetActiveObject()
        if spec is None:
            hdtv.ui.warn("No active spectrum")
        try:
            iter(ids)
        except TypeError:
            ids = [ids]
        for ID in ids:
            fit = spec.dict[ID]
            fit.fitter.ResetParamStatus()
            fit.Refresh()

    def SetPeakModel(self, peakmodel, ids=None):
        """
        Set the peak model (function used for fitting peaks)

        If a list of ids is given, the peak model of the stored fits with that
        ids will be set. Note, that the latter will fail silently for invalid
        fit ids.
        """
        # active fit
        fit = self.spectra.workFit
        fit.fitter.SetPeakModel(peakmodel)
        fit.Refresh()
        # fit list
        if not ids:   # works for None and empty list
            return
        spec = self.spectra.GetActiveObject()
        if spec is None:
            hdtv.ui.warn("No active spectrum")
        try:
            iter(ids)
        except TypeError:
            ids = [ids]
        for ID in ids:
            fit = spec.dict[ID]
            fit.fitter.SetPeakModel(peakmodel)
            fit.Refresh()

    def SetDecomposition(self, default_enable):
        '''
        Set default decomposition display status
        '''
        # default_enable may be an hdtv.options.opt instance, so we
        # excplicitely convert to bool here
        default_enable = bool(default_enable)
        hdtv.fit.Fit.showDecomp = default_enable
        # show these decompositions for workFit
        self.ShowDecomposition(default_enable)
        # show these decompositions for all other fits
        for specID in self.spectra.ids:
            fitIDs = self.spectra.dict[specID].ids
            self.ShowDecomposition(default_enable, sid=specID, ids=fitIDs)

    def ShowDecomposition(self, enable, sid=None, ids=None):
        '''
        Show decomposition of fits
        '''

        fits = list()
        if sid is None:
            spec = self.spectra.GetActiveObject()
        else:
            spec = self.spectra.dict[sid]

        fits = list()
        if ids is None:
            if self.spectra.workFit is not None:
                fits.append(self.spectra.workFit)
        else:
            fits = [spec.dict[ID] for ID in ids]

        for fit in fits:
            fit.SetDecomp(enable)


class TvFitInterface(object):
    """
    TV style interface for fitting
    """

    def __init__(self, fitInterface):
        self.fitIf = fitInterface
        self.spectra = self.fitIf.spectra

        # Register configuration variables for fit list
        opt = hdtv.options.Option(default="ID")
        hdtv.options.RegisterOption("fit.list.sort_key", opt)

        prog = "fit execute"
        description = "(re)fit a fit"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-s", "--spectrum", action="store", default="active",
            help="Spectra to work on")
        parser.add_argument(
            "-b",
            "--background",
            action="store_true",
            default=False,
            help="fit only the background")
        parser.add_argument(
            "-q", "--quick", action="store", default=None, type=float,
            help="set position for doing a quick fit")
        parser.add_argument("-S", "--store", action="store_true", default=False,
                          help="store peak after fit")
        parser.add_argument(
            "fitids",
            default=None,
            help='id(s) of the fit(s) to (re)fit')
        hdtv.cmdline.AddCommand(prog, self.FitExecute, level=0, parser=parser)
        # the "fit execute" command is registered with level=0,
        # this allows "fit execute" to be abbreviated as "fit",
        # register all other commands starting with fit with default or higher
        # priority

        prog = "fit marker"
        description = "set/delete a marker"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument(
            "type",
            #choices=['background', 'region', 'peak'], # no autocompletion
            help='type of marker to modify (background, region, peak)')
        parser.add_argument(
            "action",
            #choices=['set', 'delete'], # no autocompletion
            help='set or delete marker')
        parser.add_argument(
            "position",
            type=float,
            help='position of marker')
        hdtv.cmdline.AddCommand(prog, self.FitMarkerChange,
            parser=parser, completer=self.MarkerCompleter)

        prog = "fit clear"
        description = "clear the active work fit"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument(
            "-b",
            "--background_only",
            action="store_true",
            default=False,
            help="clear only background fit, refit peak fit with internal background")
        hdtv.cmdline.AddCommand(prog, self.FitClear, parser=parser)

        prog = "fit store"
        description = "store the active work fit to fitlist"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument(
            "fitids",
            default=None,
            help="id(s) of fit(s) to store",
            nargs='?')
        hdtv.cmdline.AddCommand(prog, self.FitStore, parser=parser)

        prog = "fit activate"
        description = "reactivates a fit from the fitlist"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument(
            "fitids",
            default=None,
            help="id(s) of fit(s) to reactivate")
        hdtv.cmdline.AddCommand(prog, self.FitActivate, parser=parser)

        prog = "fit delete"
        description = "delete fits"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-s", "--spectrum", action="store", default="active",
            help="spectrum ids to work on")
        parser.add_argument(
            "fitids",
            default=None,
            help="id(s) of fit(s) to delete",
            nargs='+')
        hdtv.cmdline.AddCommand(prog, self.FitDelete, parser=parser)

        prog = "fit show"
        description = "display fits"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-s", "--spectrum", action="store", default="active",
            help="select spectra to work on")
        parser.add_argument(
            "-v",
            "--adjust-viewport",
            action="store_true",
            default=False,
            help="adjust viewport to include all fits")
        parser.add_argument(
            "fitids",
            default=None,
            help="id(s) of fit(s) to show")
        hdtv.cmdline.AddCommand(prog, self.FitShow, parser=parser)

        prog = "fit hide"
        description = "hide fits"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-s", "--spectrum", action="store", default="active",
            help="select spectra to work on")
        parser.add_argument(
            "fitids",
            default=None,
            help="id(s) of fit(s) to hide")
        hdtv.cmdline.AddCommand(prog, self.FitHide, parser=parser)

        prog = "fit show decomposition"
        description = "display decomposition of fits"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-s", "--spectrum", action="store", default="active",
            help="select spectra to work on")
        parser.add_argument(
            "fitids",
            default=None,
            help="id(?) of fit(s) to show decomposition of",)
        hdtv.cmdline.AddCommand(prog, self.FitShowDecomp, parser=parser)

        prog = "fit hide decomposition"
        description = "display decomposition of fits"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-s", "--spectrum", action="store", default="active",
            help="select spectra to work on")
        parser.add_argument(
            "fitids",
            default=None,
            help="id(s) of fit(s) to hide decomposition of",)
        hdtv.cmdline.AddCommand(prog, self.FitHideDecomp, parser=parser)

        prog = "fit focus"
        description = "focus on fit with id"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-s", "--spectrum", action="store", default="active",
            help="select spectra")
        parser.add_argument(
            "fitid",
            default=None,
            help="id(s) of fit(s) focus on")
        hdtv.cmdline.AddCommand(prog, self.FitFocus, parser=parser)

        prog = "fit list"
        description = "list fit results"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument(
            "-v",
            "--visible",
            action="store_true",
            default=False,
            help="only list visible fit")
        parser.add_argument(
            "-k",
            "--key-sort",
            action="store",
            default=hdtv.options.Get("fit.list.sort_key"),
            help="sort by key")
        parser.add_argument(
            "-r",
            "--reverse-sort",
            action="store_true",
            default=False,
            help="reverse the sort")
        parser.add_argument("-s", "--spectrum", action="store", default="active",
            help="select spectra to work on")
        parser.add_argument("-f", "--fit", action="store", default="all",
            help="specify which fits to list")
        # FIXME: Why use a different syntax here? --fit vs fitids
#       parser.add_argument(
#           "fitids",
#           default=None,
#           help="id(s) of fit(s) to list",
#           nargs='?')
        hdtv.cmdline.AddCommand(prog, self.FitList, parser=parser)

        prog = "fit parameter"
        description = "show status of fit parameter, reset or set parameter"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-f", "--fit", action="store", default=None,
            help="change parameter of selected fit and refit")
        parser.add_argument(
            'action',
            help='{status,reset,background,tl,vol,pos,sh,sw,tr,width}')
        parser.add_argument(
            'value_peak',
            metavar='value-peak',
            help='value of the peak to use',
            nargs='*')
        hdtv.cmdline.AddCommand(
            prog,
            self.FitParam,
            completer=self.ParamCompleter,
            parser=parser)

        prog = "fit function peak activate"
        description = "selects which peak model to use"
        parser = hdtv.cmdline.HDTVOptionParser(
            prog=prog, description=description)
        parser.add_argument("-f", "--fit", action="store", default=None,
            help="change selected fits and refit")
        parser.add_argument(
            "peakmodel",
            help="name of peak model")
        hdtv.cmdline.AddCommand(prog, self.FitSetPeakModel,
                                completer=self.PeakModelCompleter,
                                parser=parser)

    def FitMarkerChange(self, args):
        """
        Set or delete a marker from command line
        """
        # first argument is marker type name
        mtype = args.type
        # complete markertype if needed
        mtype = self.MarkerCompleter(mtype)
        if len(mtype) == 0:
            raise hdtv.cmdline.HDTVCommandError("Markertype %s is not valid" % args.type)
        # second argument is action
        action = self.MarkerCompleter(args.action, args=[args.action,])
        if len(action) == 0:
            raise hdtv.cmdline.HDTVCommandError("Invalid action: %s" % args.action)
        # parse position
        pos = args.position
        
        mtype = mtype[0].strip()
        # replace "background" with "bg" which is internally used
        if mtype == "background":
            mtype = "bg"
        action = action[0].strip()
        if action == "set":
            self.spectra.SetMarker(mtype, pos)
        if action == "delete":
            self.spectra.RemoveMarker(mtype, pos)

    def MarkerCompleter(self, text, args=[]):
        """
        Helper function for FitMarkerChange
        """
        if not args:
            mtypes = ["background", "region", "peak"]
            return hdtv.util.GetCompleteOptions(text, mtypes)
        elif len(args) == 1:
            actions = ["set", "delete"]
            return hdtv.util.GetCompleteOptions(text, actions)

    def FitExecute(self, args):
        """
        Execute a fit
        """
        specIDs = hdtv.util.ID.ParseIds(args.spectrum, self.spectra)
        if len(specIDs) == 0:
            hdtv.ui.warn("No spectrum to work on")
            return
        if args.background:
            doPeaks = False
        else:
            doPeaks = True

        # Store active spec ID before activation of other spectra
        oldActiveID = self.spectra.activeID

        for specID in specIDs:
            self.spectra.ActivateObject(ID=specID)
            fitIDs = hdtv.util.ID.ParseIds(
                args.fitids, self.spectra.dict[specID])
            if len(fitIDs) == 0:
                if args.quick is not None:
                    self.fitIf.QuickFit(args.quick)
                else:
                    self.spectra.ExecuteFit(peaks=doPeaks)

                if args.store is True:   # Needed when args.quick is set for multiple spectra, else fits will be lost
                    self.spectra.StoreFit()  # Store current fit

            for fitID in fitIDs:
                try:
                    hdtv.ui.msg("Executing fit %s in spectrum %s" %
                                (fitID, specID))
                    self.fitIf.ExecuteRefit(
                        specID=specID, fitID=fitID, peaks=doPeaks)
                except (KeyError, RuntimeError) as e:
                    hdtv.ui.warn(e)
                    continue

        if oldActiveID is not None:  # Reactivate spectrum that was active in the beginning
            self.spectra.ActivateObject(ID=oldActiveID)
        return None

    def FitClear(self, args):
        """
        Clear work fit
        """
        self.spectra.ClearFit(args.background_only)

    def FitStore(self, args):
        """
        Store work fit
        """
        try:
            self.spectra.StoreFit(args.fitids)
        except IndexError:
            return

    def FitActivate(self, args):
        """
        Activate a fit

        This marks a stored fit as active and copies its markers to the work Fit
        """
        sid = self.spectra.activeID
        if sid is None:
            hdtv.ui.warn("No active spectrum")
            return
        spec = self.spectra.dict[sid]
        ids = hdtv.util.ID.ParseIds(args.fitids, spec)
        if len(ids) == 1:
            hdtv.ui.msg("Activating fit %s" % ids[0])
            self.spectra.ActivateFit(ids[0], sid)
        elif len(ids) == 0:
            hdtv.ui.msg("Deactivating fit")
            self.spectra.ActivateFit(None, sid)
        else:
            raise hdtv.cmdline.HDTVCommandError("Can only activate one fit")

    def FitDelete(self, args):
        """
        Delete fits
        """
        sids = hdtv.util.ID.ParseIds(args.spectrum, self.spectra)
        if len(sids) == 0:
            hdtv.ui.warn("No spectra chosen or active")
            return
        else:
            for s in sids:
                spec = self.spectra.dict[s]
                fitids = hdtv.util.ID.ParseIds(
                    args.fitids, spec, only_existent=False)
                already_removed = set()
                for fitid in fitids:
                    # only whole fits can be removed not single peaks
                    if fitid.minor is not None:
                        if fitid.major in already_removed:
                            continue
                        else:
                            msg = "It is not possible to remove single peaks, "
                            msg += "removing whole fit with id %s instead." % fitid.major
                            hdtv.ui.warn(msg)
                            fitid.minor = None
                            already_removed.add(fitid.major)
                    # do the work
                    spec.Pop(fitid)

    def FitHide(self, args):
        """
        Hide Fits
        """
        # FitHide is the same as FitShow, except that the spectrum selection is
        # inverted
        self.FitShow(args, inverse=True)

    def FitShow(self, args, inverse=False):
        """
        Show Fits

        inverse = True inverses the fit selection i.e. FitShow becomes FitHide
        """
        sids = hdtv.util.ID.ParseIds(args.spectrum, self.spectra)
        for sid in sids:
            spec = self.spectra.dict[sid]
            fitids = hdtv.util.ID.ParseIds(args.fitids, spec)
            if inverse:
                spec.HideObjects(fitids)
            else:
                spec.ShowObjects(fitids)
                if args.adjust_viewport:
                    fits = [spec.dict[fitid] for fitid in fitids]
                    self.spectra.window.FocusObjects(fits)

    def FitHideDecomp(self, args):
        """
        Hide decomposition of fits
        """
        self.FitShowDecomp(args, show=False)

    def FitShowDecomp(self, args, show=True):
        """
        Show decomposition of fits

        show = False hides decomposition
        """
        sids = hdtv.util.ID.ParseIds(args.spectrum, self.spectra)
        for sid in sids:
            spec = self.spectra.dict[sid]
            fitIDs = hdtv.util.ID.ParseIds(args.fitids, spec)

            if len(fitIDs) == 0:
                fitIDs = None
            self.fitIf.ShowDecomposition(show, sid=sid, ids=fitIDs)

    def FitFocus(self, args):
        """
        Focus a fit.

        If no fit is given focus the active fit.
        """
        sids = hdtv.util.ID.ParseIds(args.spectrum, self.spectra)

        fits = list()
        if len(args.fitid) == 0:
            fits.append(self.spectra.workFit)
            spec = self.spectra.GetActiveObject()
            activeFit = spec.GetActiveObject()
            if activeFit is not None:
                fit.append(activeFit)
        else:
            for sid in sids:
                spec = self.spectra.dict[sid]
                ids = hdtv.util.ID.ParseIds(args.fitid, spec)
                fits.extend([spec.dict[ID] for ID in ids])
                spec.ShowObjects(ids, clear=False)
                if len(fits) == 0:
                    hdtv.ui.warn("Nothing to focus in spectrum %s" % sid)
                    return
        self.spectra.window.FocusObjects(fits)

    def FitList(self, args):
        """
        Show a nice table with the results of fits

        By default the result of the work fit is shown.
        """
        self.fitIf.PrintWorkFit()
        sids = hdtv.util.ID.ParseIds(args.spectrum, self.spectra)
        if len(sids) == 0:
            hdtv.ui.warn("No spectra chosen or active")
            return
        # parse sort_key
        key_sort = args.key_sort.lower()
        for sid in sids:
            spec = self.spectra.dict[sid]
            ids = hdtv.util.ID.ParseIds(args.fit, spec)
            if args.visible:
                ids = [ID for ID in spec.visible]
            if len(ids) == 0:
                continue
            self.fitIf.ListFits(sid, ids, sortBy=key_sort,
                                reverseSort=args.reverse_sort)

    def FitSetPeakModel(self, args):
        """
        Defines peak model to use for fitting
        """
        name = args.peakmodel.lower()
        # complete the model name if needed
        models = self.PeakModelCompleter(name)
        # check for unambiguity
        if len(models) > 1:
            raise hdtv.cmdline.HDTVCommandError("Peak model name '%s' is ambiguous" % name)
        if len(models) == 0:
            raise hdtv.cmdline.HDTVCommandError("Invalid peak model '%s'" % name)
        else:
            name = models[0].strip()
            ids = list()
            if args.fit:
                spec = self.spectra.GetActiveObject()
                if spec is None:
                    hdtv.ui.warn("No active spectrum, no action taken.")
                    return
                ids = hdtv.util.ID.ParseIds(args.fit, spec)
            self.fitIf.SetPeakModel(name, ids)

    def PeakModelCompleter(self, text, args=None):
        """
        Helper function for FitSetPeakModel
        """
        return hdtv.util.GetCompleteOptions(
            text, iter(hdtv.peakmodels.PeakModels.keys()))

    def FitParam(self, args):
        """
        Manipulate the status of fitter parameter
        """
        # first argument is parameter name
        param = args.action
        # complete the parameter name if needed
        parameter = self.ParamCompleter(param)
        # check for unambiguity
        if len(parameter) > 1:
            raise hdtv.cmdline.HDTVCommandError("Parameter name %s is ambiguous" % param)
        if len(parameter) == 0:
            raise hdtv.cmdline.HDTVCommandError("Parameter name %s is not valid" % param)
        param = parameter[0].strip()
        ids = list()
        if args.fit:
            spec = self.spectra.GetActiveObject()
            if spec is None:
                hdtv.ui.warn("No active spectrum, no action taken.")
                return
            ids = hdtv.util.ID.ParseIds(args.fit, spec)
        if param == "status":
            self.fitIf.ShowFitterStatus(ids)
        elif param == "reset":
            self.fitIf.ResetFitterParameters(ids)
        else:
            try:
                self.fitIf.SetFitterParameter(param, " ".join(args.value_peak), ids)
            except ValueError as msg:
                raise hdtv.cmdline.HDTVCommandError(msg)

    def ParamCompleter(self, text, args=None):
        """
        Creates a completer for all possible parameter names
        or valid states for a parameter (args[0]: parameter name).
        """
        if not args:
            params = ["status", "reset"]
            # create a list of all possible parameter names
            activeParams = self.spectra.workFit.fitter.params
            params.extend(activeParams)
            return hdtv.util.GetCompleteOptions(text, params)
        else:
            states = list()
            param = args[0]
            if params == "background":
                return hdtv.util.GetCompleteOptions(text, states)
            else:
                activePM = self.spectra.workFit.fitter.peakModel
                try:
                    states = activePM.fValidParStatus[param]
                except KeyError:
                    # param is not a parameter of the peak model of active
                    # fitter
                    msg = "Invalid parameter %s for active peak model %s" % (
                        param, activePM.name)
                    hdtv.ui.error(msg)
                # remove <type: float> option
                states.remove(float)
                return hdtv.util.GetCompleteOptions(text, states)

    def ResetFit(self, args):
        """
        Reset fitter of a fit to unfitted default.
        """
        specIDs = hdtv.util.ID.ParseIds(args.spectrum, self.spectra)
        if len(specIDs) == 0:
            raise hdtv.cmdline.HDTVCommandError("No spectrum to work on")
        for specID in specIDs:
            fitIDs = hdtv.util.ID.ParseIds(args.fitids, self.spectra.dict[specID])
            if len(fitIDs) == 0:
                hdtv.ui.warn("No fit for spectrum %d to work on", specID)
                continue
            for fitID in fitIDs:
                self.fitIf.FitReset(specID=specID, fitID=fitID,
                                    resetFitter=not args.keep_fitter)


# plugin initialisation
import __main__
__main__.f = FitInterface(__main__.spectra)
