with Geometry;

package Circles is
   type Circle is new Geometry.Shape with record
      Radius : Float := 1.0;
   end record;

   overriding procedure Draw (Self : in Circle);
   function Create (Radius : in Float) return Circle;
end Circles;
