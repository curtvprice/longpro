# process DEM value
import os
import arcpy
from arcpy import env
from arcpy.sa import *

def gpmsg(msg=None):
    if msg: 
        arcpy.AddMessage(msg)
    else:
        arcpy.AddMessage(arcpy.GetMessages(0))
    
def shedpath(shed_folder, vslice="12.2", *derived):
    """Build watershed flowlength and mainstem"""
    try:
        ofolder = shed_folder
        vslice = float(vslice)
        
        env.workspace = ofolder
        env.scratchWorkspace = ofolder
        ogdb = os.path.join(ofolder, "watershed.gdb")

        # calculate flow length
        gpmsg("Flow length ...")
        flen = FlowLength("fdr.tif", "DOWNSTREAM")
        flen.save("len.tif")
        gpmsg("Flow length complete.")

        cellSize = flen.meanCellHeight
        
        # trace down from most upstream network cell, this is the mainstem
        net = Raster(os.path.join(env.workspace, "net.tif"))
        wsh = Raster(os.path.join(env.workspace, "wsh.tif"))
        fdr = Raster(os.path.join(env.workspace, "fdr.tif"))
        # extract flow length in synthetic stream net
        flen1 = ExtractByMask(flen, net)
        headcell = Con(flen1 == flen1.maximum, 1)
        main = CostPath(headcell, wsh, fdr, "EACH_ZONE")
        main1 = SetNull(IsNull(main), 1)
        main1.save("stm.tif")
        gpmsg("mainstem raster: stm.tif")
        mainstem = StreamToFeature(main1, fdr, os.path.join(ogdb, "mainstem"), "NO_SIMPLIFY")
        gpmsg("stream to feature: mainstem")

        # create elevation profile table
        arcpy.AddMessage("Sample: mainstem_profile")
        profile_tbl = os.path.join(ogdb, "mainstem_profile_tmp")
        tbl = Sample([flen, "ele.tif", "fil.tif", "fac.tif"], "stm.tif", profile_tbl)
        arcpy.management.AddField(tbl, "NAME", "TEXT", "", "", 24)
        arcpy.management.AddField(tbl, "LENKM", "FLOAT")
        arcpy.management.AddField(tbl, "ELEV", "FLOAT")
        arcpy.management.AddField(tbl, "ELEVFIL", "FLOAT")
        arcpy.management.AddField(tbl, "ELEVS", "FLOAT")        
        arcpy.management.AddField(tbl, "AREAKM2", "FLOAT")
        expr = "'{}'".format(os.path.basename(shed_folder))
        arcpy.management.CalculateField(tbl, "NAME", expr, "PYTHON")
        arcpy.management.CalculateField(tbl, "LENKM", "!LEN_BAND_1! / 1000.0", "PYTHON")
        arcpy.management.CalculateField(tbl, "ELEV", "!ELE_BAND_1! / 100.0", "PYTHON")
        expr = "{0} * ((!ELE_BAND_1! / 100.0) // {0})".format(vslice)
        arcpy.management.CalculateField(tbl, "ELEVFIL", "!FIL_BAND_1! / 100.0", "PYTHON")
        arcpy.management.CalculateField(tbl, "ELEVS", expr, "PYTHON")
        expr = "!FAC_BAND_1! * {0} * {0} / 1.0e6".format(cellSize)
        arcpy.management.CalculateField(tbl, "AREAKM2", expr, "PYTHON")
        droplist = ["STM_TIF", "LEN_BAND_1", "ELE_BAND_1", "FIL_BAND_1","FAC_BAND_1"]
        arcpy.management.DeleteField(tbl, droplist)

        # add segments  to table using provided interval (m) and downstream river-km
        arcpy.management.AddField(tbl, "SEG", "LONG")
        expr = "{0} * int(!ELEV! / {0})".format(vslice)
        arcpy.management.CalculateField(tbl, "SEG", expr, "PYTHON")
        tbl1 = profile_tbl.replace("_tmp","")
        arcpy.management.Sort(tbl, tbl1, "SEG;LENKM")
        arcpy.management.Delete(tbl)
        
        # summarize by segment
        segtbl = os.path.join(ogdb, "mainstem_seg")
        stats = ("LENKM MIN; LENKM MAX;"
                 "ELEV MIN;ELEV MAX;AREAKM2 MIN;AREAKM2 MAX;"
                 "X FIRST;Y FIRST")
        arcpy.analysis.Statistics(tbl1, segtbl, stats, "SEG")
        tvSeg = arcpy.management.MakeTableView(segtbl, "tvSeg")

        # calculate Acent (area est in middle of segment)
        arcpy.management.AddField(tvSeg, "ACENT", "FLOAT")
        codeblock = """
from math import log10
def f(a1, a2):
    return 10**((log10(a1) + log10(a2)) / 2)
        """
        expr = "f(!MIN_AREAKM2!, !MAX_AREAKM2!)"
        arcpy.management.CalculateField(tvSeg, "ACENT", expr, "PYTHON", codeblock)      
        
        # calculate slope in percent for each segment
        arcpy.management.AddField(tvSeg, "SLPPCT", "FLOAT")
        expr = "(!MAX_ELEV! - !MIN_ELEV!) / (1000 * (!MAX_LENKM! - !MIN_LENKM!))"
        arcpy.management.CalculateField(tvSeg, "SLPPCT", expr, "PYTHON")

        # create feature class of points at bottom of each segment (first xy)
        SR = arcpy.Describe(mainstem).spatialReference
        mainstem_point = os.path.join(ogdb, "mainstem_point")
        # remove points with invalid slopes (headwater and flat segments)
        expr = "SLPPCT IS NOT NULL OR SLPPCT > 0"
        arcpy.management.SelectLayerByAttribute(tvSeg, "", expr)
        arcpy.management.XYTableToPoint(tvSeg, mainstem_point,  "FIRST_X", "FIRST_Y", "", SR)
        arcpy.management.Delete(tvSeg)
        arcpy.management.Delete(segtbl)
        gpmsg("points: mainstem_point")
        
        return  mainstem, profile_tbl, mainstem_point
    
    except Exception as msg:
        raise Exception(msg)

    
if __name__ == "__main__":
    # Script tool interface:
    # Get zero or more parameters as text, call tool
    numarg = arcpy.GetArgumentCount()
    argv = tuple(arcpy.GetParameterAsText(i)
        for i in range(numarg))
    mainstem, profile_tbl, mainstem_point = shedpath(*argv)
    arcpy.SetParameterAsText(numarg-3, mainstem)
    arcpy.SetParameterAsText(numarg-2, profile_tbl)
    arcpy.SetParameterAsText(numarg-1, mainstem_point)
