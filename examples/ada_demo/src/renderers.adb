with Circles;
with Geometry;

package body Renderers is
   procedure Render
     (Self : in Renderer;
      Item : in Geometry.Shape'Class)
   is
      pragma Unreferenced (Self, Item);
      Example : Circles.Circle := Circles.Create (2.0);
   begin
      Circles.Draw (Example);
   end Render;
end Renderers;
