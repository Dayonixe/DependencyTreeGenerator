with Circles;
with Renderers;

procedure Main is
   Painter : Renderers.Renderer;
   Item    : Circles.Circle := Circles.Create (3.0);
begin
   Renderers.Render (Painter, Item);
end Main;
