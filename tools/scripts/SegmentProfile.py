"""
Segment Profile
Reads a fluvial stream profile point feature class, created by the
Shed Path tool and adds an SSEG field with slope segments 
determined using regression. These default segments can be modified by 
manually modifying the SSEG values and re-running the tool with the
parameter Use Existing Segments set to true.
"""
import os
import arcpy
import numpy as np
from scipy.stats import linregress
def SegmentProfile(mainstem_point, use_existing="false", verbose="false"):
    """Script code goes below"""
    use_existing = use_existing == "true"
    verbose =  verbose == "true"
    
    # copy data from ArcGIS to python numpy arrays
    arr = arcpy.da.TableToNumPyArray(mainstem_point, ("SEG", "ACENT", "SLPPCT"))
    arr1 = np.sort(arr, order="ACENT")
    # take log10 of area and slope
    logar = np.log10(arr1["ACENT"])
    logsl = np.log10(arr1["SLPPCT"])
    # run regression on entire area-slope pairs
    
    r = linregress(logar,logsl)
    if verbose:
        arcpy.AddMessage("log10: slope: {:.3f} intercept {:.3f} pvalue {:.3f}".format(
            r.slope, r.intercept, r.pvalue))
        arcpy.AddMessage("raw:   slope: {:.3f} intercept {:.3f} pvalue {:.3f}".format(
            10**r.slope,10**r.intercept, r.pvalue))
        
    if not use_existing:
    
        # run regression on groups of points to calculate slope
        arcpy.AddMessage("Determining slope segments from stream profile...")
        gg = 7
        # gg is the window size
        ggh = gg // 2 # half window size (for gg=7, ggh=3)
        tags = [] # list of slope signs
        # start with incomplete groups (for gg=7, 4,5,6)
        for k in range(ggh+1,gg):
            r = linregress(logar[:k], logsl[:k])
            sign = int(r.slope >= 0) # 1 for non-negative, 0 for negative
            tags.append(sign)
            if verbose:
                arcpy.AddMessage("{} - {}: slope: {:.3f} intercept {:.3f} pvalue {:.3f} N:{} {}".format(
                    k, arr1["SEG"][0], r.slope, r.intercept, r.pvalue,len(logar[:k]), sign))
        # run regression on every complete window
        for k in range(len(arr1)-(gg-1)):
            r = linregress(logar[k:k+gg], logsl[k:k+gg])
            sign = int(r.slope >= 0) # 1 for non-negative, 0 for negative
            tags.append(sign)
            if verbose:
                arcpy.AddMessage("{} - {}: slope: {:.3f} intercept {:.3f} pvalue {:.3f} N:{} {}".format(
                    k, arr1["SEG"][k], r.slope, r.intercept, r.pvalue,len(logar[k:k+gg]), sign))
        # assign last incomplete point groups to slope of last complete group
        tags += [sign] * ggh
        if verbose:
            arcpy.AddMessage("tags: {}".format(tags))
        
        # at each change in tag (zero to 1 or back), set a new slope segment
        
        oids = []
        sseg = 0
        ssegs = [0]
        for i in range(1,len(tags)):
            if tags[i-1] != tags[i]:
                oids.append(arr1["SEG"][i])
                sseg += 1
            ssegs.append(sseg)
        ssegs1 = np.array(ssegs)
            
    else:
        arcpy.AddMessage("Using existing slope segments from field SSEG")
        segarr = arcpy.da.TableToNumPyArray(mainstem_point, ("SSEG", "ACENT"))
        segarr1 = np.sort(segarr, order="ACENT")
        ssegs1 = segarr1["SSEG"].astype(int)
        
        
    # report slope segments
    
    seglist = list(set(ssegs1)) # unique list of slope segments
    #arcpy.AddMessage("SEG IN {}".format(tuple(oids))) # select expression for use in ArcGIS checking
    arcpy.AddMessage("{} slope segments found".format(len(seglist)))
    if verbose:
        arcpy.AddMessage(seglist)
    
    # run regressions on each slope segment, these are our ks results
    
    arcpy.AddMessage("Regressions for each slope segment:")
    
    for k in seglist:
        xsel = arr1[ssegs1 == k]
        xlogar = logar[ssegs1 == k]
        xlogsl = logsl[ssegs1 == k]
        r = linregress(xlogar,xlogsl)
        arcpy.AddMessage("sseg {} {} npts: {:2} slope: {:7.3f} intercept {:7.3f} pvalue {:6.3f}".format(
            k, xsel["SEG"][0], len(xlogar), r.slope, r.intercept, r.pvalue))
    
    if not use_existing:
        # convert results to a structured array, copy data back to ArcGIS table
        
        arcpy.AddMessage("Adding segment tags to {}".format(mainstem_point))
        arr2 = []
        for i,k in enumerate(ssegs1):
            arr2.append((arr1["SEG"][i],k))
        arr2 = np.array(arr2)
        arr3 = numpy.core.records.fromarrays(
            arr2.transpose(), numpy.dtype([("SEG", "i4"), ("SSEG", "i4")]))
        gdb = "memory"
        tmp_tbl = gdb + "\\" + "tmp_out"
        if arcpy.Exists(tmp_tbl):
            arcpy.management.Delete(tmp_tbl)
        arcpy.da.NumPyArrayToTable(arr3, tmp_tbl)
        if arcpy.ListFields(mainstem_point,"SSEG"):
            arcpy.management.DeleteField("mainstem_point", "SSEG")
        arcpy.management.JoinField(mainstem_point, "SEG", tmp_tbl, "SEG", "SSEG")
        arcpy.management.Delete(tmp_tbl)
    
    mainstem_point = arcpy.Describe(mainstem_point).catalogPath
    return mainstem_point
    
if __name__ == "__main__":
    mainstem_point = arcpy.GetParameterAsText(0)
    use_existing = arcpy.GetParameterAsText(1)
    result = SegmentProfile(mainstem_point, use_existing)
    arcpy.SetParameterAsText(2, result)
