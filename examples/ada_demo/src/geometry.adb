with Ada.Text_IO;

package body Geometry is
   procedure Draw (Self : in Shape) is
      pragma Unreferenced (Self);
   begin
      Ada.Text_IO.Put_Line ("shape");
   end Draw;
end Geometry;
