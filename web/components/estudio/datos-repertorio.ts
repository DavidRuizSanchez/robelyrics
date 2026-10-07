// Cifras del estudio del repertorio en directo. Todas salen de
// `api/scripts/pr/build_study_dataset.py` y `analyze_geography.py`, y cada una
// está trazada en `data/estudio/SOURCES.md` con su fuente, periodo y hora de
// extracción. No se tocan a mano: si cambia el dato, se regenera el script.

/** [título, disco · año, toques Extremoduro, toques Robe] */
export type FilaApilada = [string, string, number, number];
/** [título, disco · año, toques, % de conciertos de Extremoduro] */
export type FilaAtras = [string, string, number, number];
/** [título, % conciertos Extremoduro 2008-2014, % conciertos Robe, índice] */
export type FilaDumbbell = [string, number, number, string];
/** [disco, interpretaciones, % del total] */
export type FilaDisco = [string, number, number];
/** [título, disco · año, verso] */
export type FilaOnce = [string, string, string];

export type Provincia = {
  n: number;
  ciudades: { c: string; n: number }[];
  n_ciudades: number;
  primer: string;
  ultimo: string;
};

export const TOP: FilaApilada[] = [
  ["Ama, ama, ama y ensancha el alma","Deltoya · 1992",143,94],
  ["Dulce introducción al caos","La ley innata · 2008",103,58],
  ["Jesucristo García","Tú en tu casa, nosotros en la hoguera · 1990",130,28],
  ["Standby","Yo, minoría absoluta · 2002",117,37],
  ["Salir","Canciones prohibidas · 1998",123,24],
  ["La vereda de la puerta de atrás","Yo, minoría absoluta · 2002",97,42],
  ["Puta","Yo, minoría absoluta · 2002",116,20],
  ["So payaso","Agila · 1996",86,27],
  ["Si te vas…","Material defectuoso · 2011",35,78],
  ["Buscando una luna","Agila · 1996",98,14],
  ["Sol de invierno","Deltoya · 1992",107,0],
  ["Golfa","Canciones prohibidas · 1998",85,18],
];
export const ATRAS: FilaAtras[] = [
  ["Sol de invierno","Deltoya · 1992",107,23.3],
  ["Deltoya","Deltoya · 1992",91,19.8],
  ["Pedrá","Pedrá · 1995",83,18.1],
  ["Quemando tus recuerdos","Somos unos animales · 1991",76,16.6],
  ["Autorretrato","Canciones prohibidas · 1998",72,15.7],
  ["Pepe Botika","¿Dónde están mis amigos? · 1993",71,15.5],
  ["Amor castúo","Tú en tu casa, nosotros en la hoguera · 1990",61,13.3],
  ["J.D. La Central Nuclear","Somos unos animales · 1991",57,12.4],
  ["Primer movimiento: El sueño","La ley innata · 2008",57,12.4],
  ["De acero","Deltoya · 1992",47,10.2],
];
// Extremoduro 2008-2014 (107 conciertos con repertorio completo) frente a todo
// Robe (132). Dividir por los 459 setlists registrados daba «Contra todos» ×17,7
// cuando la cifra comparable es ×4,1: la mayoría de las fichas antiguas no
// listan el repertorio.
export const DUMB: FilaDumbbell[] = [
  ["Contra todos",10.3,42.4,"4,1"],
  ["Si te vas…",32.7,59.1,"1,8"],
  ["Ama, ama, ama y ensancha el alma",96.3,71.2,"0,7"],
  ["Tango suicida",24.3,15.2,"0,6"],
  ["El camino de las utopías",51.4,27.3,"0,5"],
  ["Dulce introducción al caos",96.3,43.9,"0,5"],
  ["La vereda de la puerta de atrás",81.3,31.8,"0,4"],
  ["Standby",98.1,28.0,"0,3"],
  ["Puta",97.2,15.2,"0,2"],
  ["Salir",97.2,18.2,"0,2"],
];
export const DISCO_E: FilaDisco[] = [["Deltoya",465,14.1],["Yo, minoría absoluta",418,12.7],["Agila",402,12.2],
  ["Canciones prohibidas",332,10.1],["Tú en tu casa, nosotros en la hoguera",302,9.2],
  ["La ley innata",298,9.0],["Para todos los públicos",269,8.2],["Somos unos animales",240,7.3],
  ["¿Dónde están mis amigos?",194,5.9],["Versiones y otros",170,5.2],["Material defectuoso",121,3.7],
  ["Pedrá",83,2.5],["Rock transgresivo",1,0.0]];
export const DISCO_R: FilaDisco[] = [["Versiones y otros",667,29.2],["Mayéutica",466,20.4],
  ["Destrozares, canciones para el final de los tiempos",401,17.5],
  ["Se nos lleva el aire",382,16.7],["Lo que aletea en nuestras cabezas",370,16.2]];


export const ONCE: FilaOnce[] = [
  ["Volando solo","Deltoya · 1992","Nunca estoy solo con nadie"],
  ["Estoy muy bien","¿Dónde están mis amigos? · 1993","Estoy aquí, estoy, estoy, es"],
  ["Islero, shirlero o ladrón","¿Dónde están mis amigos? · 1993","Hay que comerse los cojones a bocados"],
  ["Sin dios ni amo","¿Dónde están mis amigos? · 1993","Voy a dejar esta ciudad, no me pienso despedir"],
  ["Adiós abanico, que llegó el aire","Rock Transgresivo · 1994","Ella, entretanto, duerme casi, casi siempre sola"],
  ["Caballero andante","Rock Transgresivo · 1994","Ni tú ni yo ni perro que nos ladre, ni el calor del sol"],
  ["Érase una vez","Canciones prohibidas · 1998","Sigue tú inventando el cuento"],
  ["Buitre no come alpiste","Yo, minoría absoluta · 2002","Que estás más loca que yo"],
  ["Cerca del suelo","Yo, minoría absoluta · 2002","Y esta sí que salió bien…"],
  ["Luce la oscuridad","Yo, minoría absoluta · 2002","Luce la oscuridad; luz de las velas"],
  ["Manué IV","Para todos los públicos · 2013","Qué pena que nadie nos fusile al alba"],
];

export const PROV: Record<string, Provincia> = {"Santa Cruz de Tenerife": {"n": 5, "ciudades": [{"c": "San Cristóbal de La Laguna", "n": 3}, {"c": "Santa Cruz de Tenerife", "n": 2}], "n_ciudades": 2, "primer": "2004", "ultimo": "2024"}, "Las Palmas": {"n": 10, "ciudades": [{"c": "Las Palmas de Gran Canaria", "n": 7}, {"c": "Arrecife", "n": 1}, {"c": "San Bartolomé", "n": 1}], "n_ciudades": 4, "primer": "1993", "ultimo": "2024"}, "Barcelona": {"n": 33, "ciudades": [{"c": "Barcelona", "n": 19}, {"c": "Badalona", "n": 4}, {"c": "Terrassa", "n": 2}], "n_ciudades": 10, "primer": "1989", "ultimo": "2024"}, "Pontevedra": {"n": 12, "ciudades": [{"c": "Vigo", "n": 8}, {"c": "Pontevedra", "n": 3}, {"c": "Oia", "n": 1}], "n_ciudades": 3, "primer": "1993", "ultimo": "2024"}, "Asturias": {"n": 13, "ciudades": [{"c": "Gijón", "n": 8}, {"c": "Avilés", "n": 3}, {"c": "Oviedo", "n": 1}], "n_ciudades": 4, "primer": "1995", "ultimo": "2022"}, "Castellón": {"n": 11, "ciudades": [{"c": "Vila-real", "n": 4}, {"c": "Onda", "n": 3}, {"c": "Almassora", "n": 2}], "n_ciudades": 5, "primer": "1993", "ultimo": "2022"}, "Sevilla": {"n": 14, "ciudades": [{"c": "Sevilla", "n": 12}, {"c": "Dos Hermanas", "n": 1}, {"c": "Mairena del Aljarafe", "n": 1}], "n_ciudades": 3, "primer": "1992", "ultimo": "2022"}, "Granada": {"n": 16, "ciudades": [{"c": "Granada", "n": 11}, {"c": "Armilla", "n": 2}, {"c": "Alhendín", "n": 1}], "n_ciudades": 5, "primer": "1992", "ultimo": "2024"}, "Valladolid": {"n": 13, "ciudades": [{"c": "Valladolid", "n": 13}], "n_ciudades": 1, "primer": "1992", "ultimo": "2024"}, "La Rioja": {"n": 13, "ciudades": [{"c": "Logroño", "n": 10}, {"c": "Alfaro", "n": 1}, {"c": "Pradejón", "n": 1}], "n_ciudades": 4, "primer": "1993", "ultimo": "2024"}, "Vizcaya": {"n": 16, "ciudades": [{"c": "Bilbao", "n": 11}, {"c": "Barakaldo", "n": 2}, {"c": "Guernica", "n": 1}], "n_ciudades": 5, "primer": "1993", "ultimo": "2024"}, "Madrid": {"n": 48, "ciudades": [{"c": "Madrid", "n": 34}, {"c": "Leganés", "n": 6}, {"c": "Rivas-Vaciamadrid", "n": 3}], "n_ciudades": 6, "primer": "1989", "ultimo": "2024"}, "Badajoz": {"n": 11, "ciudades": [{"c": "Mérida", "n": 4}, {"c": "Badajoz", "n": 4}, {"c": "Don Benito", "n": 1}], "n_ciudades": 5, "primer": "1993", "ultimo": "2024"}, "Ciudad Real": {"n": 9, "ciudades": [{"c": "Daimiel", "n": 5}, {"c": "Alcázar de San Juan", "n": 3}, {"c": "Ciudad Real", "n": 1}], "n_ciudades": 3, "primer": "1993", "ultimo": "2022"}, "Almería": {"n": 7, "ciudades": [{"c": "Almería", "n": 6}, {"c": "Chirivel", "n": 1}], "n_ciudades": 2, "primer": "1999", "ultimo": "2024"}, "Albacete": {"n": 11, "ciudades": [{"c": "Albacete", "n": 7}, {"c": "Villarrobledo", "n": 3}, {"c": "Almansa", "n": 1}], "n_ciudades": 3, "primer": "1995", "ultimo": "2024"}, "Alicante": {"n": 18, "ciudades": [{"c": "Alicante", "n": 8}, {"c": "Villena", "n": 3}, {"c": "Muchamiel", "n": 1}], "n_ciudades": 9, "primer": "1990", "ultimo": "2024"}, "Girona": {"n": 10, "ciudades": [{"c": "Girona", "n": 4}, {"c": "Sant Feliu de Guíxols", "n": 3}, {"c": "Salt", "n": 2}], "n_ciudades": 4, "primer": "1996", "ultimo": "2024"}, "Tarragona": {"n": 8, "ciudades": [{"c": "Tarragona", "n": 3}, {"c": "Reus", "n": 2}, {"c": "Salou", "n": 1}], "n_ciudades": 5, "primer": "1991", "ultimo": "2014"}, "Málaga": {"n": 11, "ciudades": [{"c": "Málaga", "n": 9}, {"c": "Coín", "n": 1}, {"c": "Ronda", "n": 1}], "n_ciudades": 3, "primer": "1993", "ultimo": "2024"}, "Cádiz": {"n": 12, "ciudades": [{"c": "Cádiz", "n": 6}, {"c": "Jerez de la Frontera", "n": 2}, {"c": "Villamartín", "n": 1}], "n_ciudades": 6, "primer": "1991", "ultimo": "2024"}, "Baleares": {"n": 10, "ciudades": [{"c": "Palma", "n": 8}, {"c": "Porreres", "n": 1}, {"c": "Mallorca", "n": 1}], "n_ciudades": 3, "primer": "1992", "ultimo": "2024"}, "A Coruña": {"n": 20, "ciudades": [{"c": "A Coruña", "n": 12}, {"c": "Santiago de Compostela", "n": 6}, {"c": "Ferrol", "n": 1}], "n_ciudades": 4, "primer": "1992", "ultimo": "2024"}, "León": {"n": 10, "ciudades": [{"c": "León", "n": 6}, {"c": "Ponferrada", "n": 3}, {"c": "Quintanilla de Somoza", "n": 1}], "n_ciudades": 3, "primer": "1992", "ultimo": "2014"}, "Huelva": {"n": 3, "ciudades": [{"c": "Huelva", "n": 2}, {"c": "La Rábida", "n": 1}], "n_ciudades": 2, "primer": "1996", "ultimo": "2017"}, "Guipúzcoa": {"n": 13, "ciudades": [{"c": "San Sebastián", "n": 7}, {"c": "Irun", "n": 2}, {"c": "Bergara", "n": 1}], "n_ciudades": 6, "primer": "1993", "ultimo": "2024"}, "Burgos": {"n": 12, "ciudades": [{"c": "Burgos", "n": 6}, {"c": "Aranda de Duero", "n": 2}, {"c": "Briviesca", "n": 2}], "n_ciudades": 4, "primer": "1991", "ultimo": "2022"}, "Salamanca": {"n": 7, "ciudades": [{"c": "Salamanca", "n": 7}], "n_ciudades": 1, "primer": "1996", "ultimo": "2024"}, "Murcia": {"n": 20, "ciudades": [{"c": "Murcia", "n": 8}, {"c": "Alcantarilla", "n": 2}, {"c": "Yecla", "n": 2}], "n_ciudades": 10, "primer": "1995", "ultimo": "2024"}, "Valencia": {"n": 22, "ciudades": [{"c": "Valencia", "n": 12}, {"c": "Beniparrell", "n": 2}, {"c": "Paiporta", "n": 1}], "n_ciudades": 10, "primer": "1993", "ultimo": "2024"}, "Navarra": {"n": 13, "ciudades": [{"c": "Pamplona", "n": 9}, {"c": "Puente la Reina", "n": 2}, {"c": "Lesaka", "n": 1}], "n_ciudades": 4, "primer": "1993", "ultimo": "2024"}, "Cantabria": {"n": 10, "ciudades": [{"c": "Santander", "n": 4}, {"c": "Torrelavega", "n": 2}, {"c": "Sarón", "n": 1}], "n_ciudades": 6, "primer": "1995", "ultimo": "2024"}, "Cáceres": {"n": 37, "ciudades": [{"c": "Cáceres", "n": 15}, {"c": "Plasencia", "n": 11}, {"c": "Hervás", "n": 3}], "n_ciudades": 11, "primer": "1987", "ultimo": "2024"}, "Córdoba": {"n": 3, "ciudades": [{"c": "Córdoba", "n": 1}, {"c": "Montalbán de Córdoba", "n": 1}, {"c": "Pozoblanco", "n": 1}], "n_ciudades": 3, "primer": "2014", "ultimo": "2022"}, "Zaragoza": {"n": 15, "ciudades": [{"c": "Zaragoza", "n": 15}], "n_ciudades": 1, "primer": "1993", "ultimo": "2024"}, "Lleida": {"n": 4, "ciudades": [{"c": "Lleida", "n": 3}, {"c": "Tàrrega", "n": 1}], "n_ciudades": 2, "primer": "1999", "ultimo": "2008"}, "Palencia": {"n": 1, "ciudades": [{"c": "Palencia", "n": 1}], "n_ciudades": 1, "primer": "2008", "ultimo": "2008"}, "Segovia": {"n": 3, "ciudades": [{"c": "Segovia", "n": 3}], "n_ciudades": 1, "primer": "1995", "ultimo": "2008"}, "Soria": {"n": 4, "ciudades": [{"c": "Soria", "n": 3}, {"c": "Almazán", "n": 1}], "n_ciudades": 2, "primer": "1999", "ultimo": "2008"}, "Toledo": {"n": 9, "ciudades": [{"c": "Toledo", "n": 5}, {"c": "Talavera de la Reina", "n": 2}, {"c": "Recas", "n": 1}], "n_ciudades": 4, "primer": "1989", "ultimo": "2024"}, "Ávila": {"n": 2, "ciudades": [{"c": "Ávila", "n": 1}, {"c": "Candeleda", "n": 1}], "n_ciudades": 2, "primer": "2002", "ultimo": "2008"}, "Guadalajara": {"n": 3, "ciudades": [{"c": "Guadalajara", "n": 2}, {"c": "Cabanillas del Campo", "n": 1}], "n_ciudades": 2, "primer": "1993", "ultimo": "2022"}, "Lugo": {"n": 2, "ciudades": [{"c": "Lugo", "n": 2}], "n_ciudades": 1, "primer": "2002", "ultimo": "2008"}, "Álava": {"n": 10, "ciudades": [{"c": "Vitoria-Gasteiz", "n": 10}], "n_ciudades": 1, "primer": "1990", "ultimo": "2024"}, "Jaén": {"n": 6, "ciudades": [{"c": "Jaén", "n": 4}, {"c": "Úbeda", "n": 2}], "n_ciudades": 2, "primer": "1993", "ultimo": "2024"}, "Teruel": {"n": 2, "ciudades": [{"c": "Alcañiz", "n": 1}, {"c": "Teruel", "n": 1}], "n_ciudades": 2, "primer": "2002", "ultimo": "2022"}, "Huesca": {"n": 5, "ciudades": [{"c": "Huesca", "n": 2}, {"c": "Binéfar", "n": 2}, {"c": "Fraga", "n": 1}], "n_ciudades": 3, "primer": "1992", "ultimo": "2002"}, "Zamora": {"n": 3, "ciudades": [{"c": "Zamora", "n": 3}], "n_ciudades": 1, "primer": "1991", "ultimo": "2022"}, "Ourense": {"n": 2, "ciudades": [{"c": "Ourense", "n": 2}], "n_ciudades": 1, "primer": "1999", "ultimo": "2002"}, "Cuenca": {"n": 6, "ciudades": [{"c": "Cuenca", "n": 6}], "n_ciudades": 1, "primer": "1996", "ultimo": "2024"}};

export const CIUDADES: [string, string, number, number][] = [["Madrid","34 conciertos",34,0],["Barcelona","19",19,0],["Cáceres","15",15,0],
  ["Zaragoza","15",15,0],["Valladolid","13",13,0],["Sevilla","12",12,0],["A Coruña","12",12,0],
  ["Valencia","12",12,0],["Granada","11",11,0],["Bilbao","11",11,0],["Plasencia","11",11,0],
  ["Logroño","10",10,0],["Vitoria-Gasteiz","10",10,0],["Málaga","9",9,0],["Pamplona","9",9,0]];
export const RECINTOS: [string, string, number, number][] = [["Sala Zeleste","Barcelona",8,0],["Coliseum da Coruña","A Coruña",7,0],
  ["Recinto Hípico","Cáceres",7,0],["Sala Canciller","Madrid",6,0],
  ["Pabellón Multiusos Sánchez Paraíso","Salamanca",5,0],["Auditorio Marina Sur","Valencia",5,0],
  ["Pabellón Príncipe Felipe","Zaragoza",5,0],
  ["Palacio de Deportes de la Comunidad","Madrid",5,0],["Fernando Buesa Arena","Vitoria-Gasteiz",5,0],
  ["Palacio de los Deportes de La Rioja","Logroño",4,0]];
export const ANIOS_E: Record<number, number> = {1987:1,1988:2,1989:10,1990:13,1991:13,1992:16,1993:34,1994:25,1995:28,
  1996:53,1997:31,1999:40,2002:49,2004:37,2008:47,2012:16,2014:44};
export const ANIOS_R: Record<number, number> = {2017:34,2021:21,2022:41,2024:36};

