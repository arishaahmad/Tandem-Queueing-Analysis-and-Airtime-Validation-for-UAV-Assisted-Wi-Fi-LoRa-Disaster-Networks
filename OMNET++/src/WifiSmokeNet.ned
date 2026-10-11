package uavwifilora;

import inet.node.inet.WirelessHost;
import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.physicallayer.wireless.ieee80211.packetlevel.Ieee80211ScalarRadioMedium;

network WifiSmokeNet
{
    parameters:
        @display("bgb=800,400");

    submodules:
        device: WirelessHost {
            @display("p=150,220");
        }

        uav: WirelessHost {
            @display("p=550,220");
        }

        radioMedium: Ieee80211ScalarRadioMedium {
            @display("p=350,80");
        }

        configurator: Ipv4NetworkConfigurator {
            @display("p=550,80");
        }
}