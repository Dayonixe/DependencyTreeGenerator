package Geometry is
   type Shape is abstract tagged null record;

   procedure Draw (Self : in Shape);
end Geometry;
