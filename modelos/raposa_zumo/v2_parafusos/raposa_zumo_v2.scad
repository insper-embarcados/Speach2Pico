// Zumo 2040: milimetros, frente=-Y, origem entre furos dianteiros.
// Selecione a peça, renderize com F6 e exporte. Não escale o conjunto:
// isso altera a furação. Escala da raposa requer revisar encaixe/folgas.
peca = "montagem"; // base, cabeca, espacador, calco, montagem
espessura = 3.2;
altura_espacador = 12;
diametro_furo = 2.6;
diametro_espacador = 6;
altura_calco = 0.8;
folga_encaixe = 0.2; // por lado
$fn=64;
furos=[[-25,0],[25,0],[-27.5,63],[27.5,63]];

module barra(a,b,l,h=espessura) {
    hull() for(p=[a,b]) translate([p[0],p[1],0]) cylinder(d=l,h=h);
}
module retangulo_arredondado(l,p,r,h) {
    hull() for(x=[-1,1],y=[-1,1])
        translate([x*(l/2-r),9+y*(p/2-r),0]) cylinder(r=r,h=h);
}
module base() {
    difference() {
        union() {
            for(s=[-1,1]) {
                pontos=[[s*25,0],[s*25.5,40],[s*22,54],[s*22,57],[s*27.5,63]];
                for(i=[0:3]) barra(pontos[i],pontos[i+1],5.5);
            }
            barra([-25,9],[25,9],6);
            retangulo_arredondado(24,18,2,espessura);
            for(p=furos) translate([p[0],p[1],0]) cylinder(d=9,h=espessura);
            translate([-4,5,espessura]) cube([8,6,2.5]);
            hull() {
                translate([-4,5,espessura+2.495]) cube([8,6,.01]);
                translate([-3.5,5.5,espessura+2.99]) cube([7,5,.01]);
            }
        }
        for(p=furos) translate([p[0],p[1],-1]) cylinder(d=diametro_furo,h=espessura+2);
    }
}
module cabeca() {
    difference() {
        import("fontes/cabeca_v1.stl");
        translate([-4-folga_encaixe,-3-folga_encaixe,-1])
            cube([8+2*folga_encaixe,6+2*folga_encaixe,4.4]);
        translate([-50,-50,39]) cube([100,100,40]);
    }
}
module espacador(h=altura_espacador) {
    difference() {
        cylinder(d=diametro_espacador,h=h);
        translate([0,0,-1]) cylinder(d=diametro_furo,h=h+2);
    }
}
if(peca=="base") base();
else if(peca=="cabeca") cabeca();
else if(peca=="espacador") espacador();
else if(peca=="calco") espacador(altura_calco);
else {
    color("crimson") translate([0,0,altura_espacador]) base();
    color("crimson") translate([0,8,altura_espacador+espessura]) cabeca();
    color("silver") for(p=furos) translate([p[0],p[1],0]) espacador();
}
