package uavwifilora;

import flora.LoRaPhy.LoRaMedium;
import flora.LoraNode.LoRaNode;
import flora.LoraNode.LoRaGW;

import inet.node.inet.StandardHost;
import inet.node.ethernet.Eth1G;
import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;


network FloraSmokeNet
{
    parameters :
        @display("bgb=800,400");
        
    submodules :
        
        uav: LoRaNode{
            @display("p=120,200");
        }
        
        baseStation:LoRaGW{
        parameters :
            numEthInterfaces =1;
         @display("p=380,200");
       }
       
       LoRaMedium: LoRaMedium {
           @display("p=250,70");
       }
       
       networkServer:StandardHost{
        parameters :
            numEthInterfaces =1;
         @display("p=650,200");
       }
       
       configurator: Ipv4NetworkConfigurator{
           @display("p=650,70");
       }
       
       connections :
           baseStation.ethg[0] <-->Eth1G
           <--> networkServer.ethg[0];
}
    
            


