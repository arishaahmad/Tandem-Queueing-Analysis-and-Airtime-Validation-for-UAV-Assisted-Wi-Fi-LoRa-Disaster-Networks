package uavwifilora;

import inet.node.inet.AdhocHost;
import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.physicallayer.wireless.ieee80211.packetlevel.Ieee80211ScalarRadioMedium;
import inet.node.inet.StandardHost;
import inet.node.ethernet.Eth1G;
import flora.LoraNode.LoRaNode;
import flora.LoraNode.LoRaGW;
import flora.LoRaPhy.LoRaMedium;

network UnifiedDisasterNet
{
    parameters:
        @display("bgb=1050,500");
    submodules:
        device: AdhocHost { @display("p=110,250"); }
        uavWifi: AdhocHost { @display("p=375,210"); }
        uavLoRa: LoRaNode { @display("p=375,335"); }
        baseStation: LoRaGW {
            parameters:
                numEthInterfaces = 1;
                @display("p=650,275");
        }
        networkServer: StandardHost {
            parameters:
                numEthInterfaces = 1;
                @display("p=900,275");
        }
        radioMedium: Ieee80211ScalarRadioMedium { @display("p=225,65"); }
        LoRaMedium: LoRaMedium { @display("p=590,65"); }
        configurator: Ipv4NetworkConfigurator { @display("p=895,65"); }
    connections:
        baseStation.ethg[0] <--> Eth1G <--> networkServer.ethg[0];
    
}
