with Geometry;

package Renderers is
   type Renderer is tagged null record;

   procedure Render
     (Self : in Renderer;
      Item : in Geometry.Shape'Class);
end Renderers;
