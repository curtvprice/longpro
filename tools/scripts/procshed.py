# process DEM value
import os
import arcpy
from arcpy import env
from arcpy.sa import *

def gpmsg(msg=None):
    if msg: arcpy.AddMessage(msg)
    arcpy.AddMessage(arcpy.GetMessages(0))
    
def eleproc(in_elev, clip_poly, seed_feature, out_folder, shed_folder_name, 
            threshkm2="5.0", zfactor="100", clip_buf="500 Meters", wshed="", streams="", ofolder=""):
    """Clip DEM to a clip polygon, build elevation derivative workspace with rasters,
    watershed boundary created from provided seed feature class."""
    try:
        ofolder = os.path.join(out_folder, shed_folder_name)
        # synthetic stream network threshhold, in km2; convert to cells
        cellSize = Raster(in_elev).meanCellHeight
        threshkm2 = float(threshkm2)
        thresh_cells = int(threshkm2 * 1.0e6 / (cellSize * cellSize))
        arcpy.AddMessage("Network threshhold: {} km2, {} cells".format(
            threshkm2, thresh_cells))
        zfactor = float(zfactor)
        
        # create output workspace
        ofolder = arcpy.management.CreateFolder(out_folder, shed_folder_name)
        ofolder = str(ofolder)
        env.workspace = ofolder
        env.scratchWorkspace = ofolder
        ogdb = arcpy.management.CreateFileGDB(ofolder, "watershed")
        ogdb = str(ogdb)
        gpmsg("Created " + ogdb)
        
        # create clip buffer
        if clip_buf:
            ele_clip = os.path.join(ogdb, "ele_clip")
            arcpy.analysis.PairwiseBuffer(clip_poly, ele_clip, clip_buf)
        else:
            arcpy.management.CopyFeatures(clip_poly, ele_clip)
        gpmsg(ele_clip)
            
        # prepare seed feature
        seed = arcpy.management.CopyFeatures(seed_feature,
                                      os.path.join(ogdb, "seed"))
        try:
            arcpy.management.AddField(seed, "SEEDID", "LONG")
            arcpy.management.CalculateField(seed, "SEEDID", "1", "PYTHON")
        except:
            pass
        

   
        # Clip DEM to clip buffer, perserve this as elev.tif
        env.extent = ele_clip
        env.snapRaster = in_elev    
        env.cellSize = in_elev
        arcpy.conversion.PolygonToRaster(ele_clip, "OBJECTID", "xmask.tif", cellsize=in_elev)
        env.extent = "xmask.tif"
        elev = ExtractByMask(in_elev, "xmask.tif")
        elev.save("elev.tif")
        arcpy.management.Delete("xmask.tif")
   
        # # Clip DEM to clip buffer, perserve this as elev.tif
        # note the tool below shifted data with arcgis pro 3.1
        # arcpy.management.Clip(in_elev, "", "elev.tif", ele_clip, "", 
            # "ClippingGeometry", "NO_MAINTAIN_EXTENT")
            
        env.extent = "elev.tif"
        env.snapRaster = "elev.tif"
        env.mask = "elev.tif"
        
        # convert Z units (meters to cm)
        if zfactor != 1:
            ele = Int((Raster("elev.tif") * zfactor) + 0.5)
            ele.save("xele.tif")
        else:
            ele = arcpy.management.CopyRaster("elev.tif", "xele.tif")
            ele = Raster(ele)
        gpmsg("xele.tif")
        
        # fill
        fil = Fill(ele)
        fil.save("xfil.tif")
        gpmsg("Fill")
        
        # flow direction
        fdr = FlowDirection(fil)
        fdr.save("xfdr.tif")
        gpmsg("FDir")

        # find watershed, create watershed polygon
        wsh = Watershed(fdr, seed, "SEEDID")
        wsh.save("wsh.tif")
        gpmsg("wsh")
        wshed = arcpy.conversion.RasterToPolygon(wsh, os.path.join(ogdb, "wshed"),
                                         "NO_SIMPLIFY", "", 'MULTIPLE_OUTER_PART')
        
        # flow accumulation
        env.mask = wsh.catalogPath
        fac = FlowAccumulation(fdr, "", "FLOAT")
        fac.save("fac.tif")
        gpmsg("fac")
        
        # stream network
        net = StreamLink(fdr, Con(fac > thresh_cells, 1))
        net.save("net.tif")
        gpmsg("net")
        env.mask = None

        
        # stream net lines
        streams = StreamToFeature(net, fdr, os.path.join(ogdb, "streams"), "NO_SIMPLIFY")
        gpmsg("streams")

        # clip elevation, fill, flowdir to watershed boundary
        arcpy.AddMessage("clip rasters...")
        ele1 = ExtractByMask(ele, wsh)
        fil1 = ExtractByMask(fil, wsh)
        fdr1 = ExtractByMask(fdr, wsh)
        ele1.save("ele.tif")
        fil1.save("fil.tif")
        fdr1.save("fdr.tif")

        # Check Results for boundary clip - should not touch or cross clip boundary
        lyrClip = arcpy.management.MakeFeatureLayer(ele_clip, "lyrClip")
        lyrShed = arcpy.management.MakeFeatureLayer(wshed, "lyrShed")
        arcpy.management.SelectLayerByLocation(lyrClip, "COMPLETELY_CONTAINS", lyrShed)
        if int(arcpy.management.GetCount(lyrClip).getOutput(0)) == 0:
            arcpy.AddWarning("Watershed boundary (wshed) touches elevation clip buffer (ele_clip)")
        

        # clean up
        arcpy.management.Delete(ele)
        arcpy.management.Delete(fil)
        arcpy.management.Delete(fdr)

        return str(wshed), str(streams), ofolder
    
    except Exception as msg:
        raise Exception(msg)

    
if __name__ == "__main__":
    # Script tool interface:
    # Get zero or more parameters as text, call tool
    argv = tuple(arcpy.GetParameterAsText(i)
        for i in range(arcpy.GetArgumentCount()))
    wshed, streams, ofolder = eleproc(*argv)
    arcpy.SetParameterAsText(len(argv)-3, wshed)
    arcpy.SetParameterAsText(len(argv)-2, streams)
    arcpy.SetParameterAsText(len(argv)-1, ofolder)
