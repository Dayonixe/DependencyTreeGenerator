with Ada.Text_IO;
with Geometry;

package body Circles is
   procedure Draw (Self : in Circle) is
   begin
      Ada.Text_IO.Put_Line (Float'Image (Self.Radius));
   end Draw;

   function Create (Radius : in Float) return Circle is
   begin
      return (Geometry.Shape with Radius => Radius);
   end Create;
end Circles;
