"""
Assign segment profile

This tool allows the user to assign segment codes to the selected points
in the mainstem_point table.
"""
import arcpy

def AssignSegment(mainstem_point, segment_code=""):

    arcpy.management.CalculateField(
        mainstem_point, "SSEG", str(segment_code))
    return arcpy.Describe(mainstem_point)
    
if __name__ == "__main__":
    mainstem_point = arcpy.GetParameterAsText(0)
    segment_code = arcpy.GetParameterAsText(1)
    result = AssignSegment(mainstem_point, segment_code)
    arcpy.SetParameterAsText(2, result)