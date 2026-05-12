// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2023 Advanced Micro Devices, Inc. All Rights Reserved.
// --------------------------------------------------------------------------------
// Tool Version: Vivado v.2023.2 (lin64) Build 4029153 Fri Oct 13 20:13:54 MDT 2023
// Date        : Mon Apr  6 13:37:27 2026
// Host        : brg-zhang-xcel.ece.cornell.edu running 64-bit Red Hat Enterprise Linux 9.1 (Plow)
// Command     : write_verilog -force -mode synth_stub
//               /home/mss464/minitpu/tpu/build/mem_system/mem_system.gen/sources_1/bd/mem_bd/ip/mem_bd_mem_top_0_0/mem_bd_mem_top_0_0_stub.v
// Design      : mem_bd_mem_top_0_0
// Purpose     : Stub declaration of top-level module interface
// Device      : xczu3eg-sbva484-1-i
// --------------------------------------------------------------------------------

// This empty module with port declaration file causes synthesis tools to infer a black box for IP.
// The synthesis directives are for Synopsys Synplify support to prevent IO buffer insertion.
// Please paste the declaration into a Verilog source file or add the file as an additional source.
(* X_CORE_INFO = "mem_top,Vivado 2023.2" *)
module mem_bd_mem_top_0_0(s00_axi_aclk, s00_axi_aresetn, 
  s00_axi_awaddr, s00_axi_awprot, s00_axi_awvalid, s00_axi_awready, s00_axi_wdata, 
  s00_axi_wstrb, s00_axi_wvalid, s00_axi_wready, s00_axi_bresp, s00_axi_bvalid, 
  s00_axi_bready, s00_axi_araddr, s00_axi_arprot, s00_axi_arvalid, s00_axi_arready, 
  s00_axi_rdata, s00_axi_rresp, s00_axi_rvalid, s00_axi_rready, s00_axis_aclk, 
  s00_axis_aresetn, s00_axis_tready, s00_axis_tdata, s00_axis_tstrb, s00_axis_tlast, 
  s00_axis_tvalid, m00_axis_aclk, m00_axis_aresetn, m00_axis_tvalid, m00_axis_tdata, 
  m00_axis_tstrb, m00_axis_tkeep, m00_axis_tlast, m00_axis_tready, s01_axi_aclk, 
  s01_axi_aresetn, s01_axi_awaddr, s01_axi_awlen, s01_axi_awsize, s01_axi_awburst, 
  s01_axi_awvalid, s01_axi_awready, s01_axi_wdata, s01_axi_wstrb, s01_axi_wlast, 
  s01_axi_wvalid, s01_axi_wready, s01_axi_bresp, s01_axi_bvalid, s01_axi_bready, 
  s01_axi_araddr, s01_axi_arlen, s01_axi_arsize, s01_axi_arburst, s01_axi_arvalid, 
  s01_axi_arready, s01_axi_rdata, s01_axi_rresp, s01_axi_rlast, s01_axi_rvalid, 
  s01_axi_rready)
/* synthesis syn_black_box black_box_pad_pin="s00_axi_aresetn,s00_axi_awaddr[5:0],s00_axi_awprot[2:0],s00_axi_awvalid,s00_axi_awready,s00_axi_wdata[31:0],s00_axi_wstrb[3:0],s00_axi_wvalid,s00_axi_wready,s00_axi_bresp[1:0],s00_axi_bvalid,s00_axi_bready,s00_axi_araddr[5:0],s00_axi_arprot[2:0],s00_axi_arvalid,s00_axi_arready,s00_axi_rdata[31:0],s00_axi_rresp[1:0],s00_axi_rvalid,s00_axi_rready,s00_axis_aresetn,s00_axis_tready,s00_axis_tdata[255:0],s00_axis_tstrb[31:0],s00_axis_tlast,s00_axis_tvalid,m00_axis_aresetn,m00_axis_tvalid,m00_axis_tdata[255:0],m00_axis_tstrb[31:0],m00_axis_tkeep[31:0],m00_axis_tlast,m00_axis_tready,s01_axi_aresetn,s01_axi_awaddr[17:0],s01_axi_awlen[7:0],s01_axi_awsize[2:0],s01_axi_awburst[1:0],s01_axi_awvalid,s01_axi_awready,s01_axi_wdata[31:0],s01_axi_wstrb[3:0],s01_axi_wlast,s01_axi_wvalid,s01_axi_wready,s01_axi_bresp[1:0],s01_axi_bvalid,s01_axi_bready,s01_axi_araddr[17:0],s01_axi_arlen[7:0],s01_axi_arsize[2:0],s01_axi_arburst[1:0],s01_axi_arvalid,s01_axi_arready,s01_axi_rdata[31:0],s01_axi_rresp[1:0],s01_axi_rlast,s01_axi_rvalid,s01_axi_rready" */
/* synthesis syn_force_seq_prim="s00_axi_aclk" */
/* synthesis syn_force_seq_prim="s00_axis_aclk" */
/* synthesis syn_force_seq_prim="m00_axis_aclk" */
/* synthesis syn_force_seq_prim="s01_axi_aclk" */;
  input s00_axi_aclk /* synthesis syn_isclock = 1 */;
  input s00_axi_aresetn;
  input [5:0]s00_axi_awaddr;
  input [2:0]s00_axi_awprot;
  input s00_axi_awvalid;
  output s00_axi_awready;
  input [31:0]s00_axi_wdata;
  input [3:0]s00_axi_wstrb;
  input s00_axi_wvalid;
  output s00_axi_wready;
  output [1:0]s00_axi_bresp;
  output s00_axi_bvalid;
  input s00_axi_bready;
  input [5:0]s00_axi_araddr;
  input [2:0]s00_axi_arprot;
  input s00_axi_arvalid;
  output s00_axi_arready;
  output [31:0]s00_axi_rdata;
  output [1:0]s00_axi_rresp;
  output s00_axi_rvalid;
  input s00_axi_rready;
  input s00_axis_aclk /* synthesis syn_isclock = 1 */;
  input s00_axis_aresetn;
  output s00_axis_tready;
  input [255:0]s00_axis_tdata;
  input [31:0]s00_axis_tstrb;
  input s00_axis_tlast;
  input s00_axis_tvalid;
  input m00_axis_aclk /* synthesis syn_isclock = 1 */;
  input m00_axis_aresetn;
  output m00_axis_tvalid;
  output [255:0]m00_axis_tdata;
  output [31:0]m00_axis_tstrb;
  output [31:0]m00_axis_tkeep;
  output m00_axis_tlast;
  input m00_axis_tready;
  input s01_axi_aclk /* synthesis syn_isclock = 1 */;
  input s01_axi_aresetn;
  input [17:0]s01_axi_awaddr;
  input [7:0]s01_axi_awlen;
  input [2:0]s01_axi_awsize;
  input [1:0]s01_axi_awburst;
  input s01_axi_awvalid;
  output s01_axi_awready;
  input [31:0]s01_axi_wdata;
  input [3:0]s01_axi_wstrb;
  input s01_axi_wlast;
  input s01_axi_wvalid;
  output s01_axi_wready;
  output [1:0]s01_axi_bresp;
  output s01_axi_bvalid;
  input s01_axi_bready;
  input [17:0]s01_axi_araddr;
  input [7:0]s01_axi_arlen;
  input [2:0]s01_axi_arsize;
  input [1:0]s01_axi_arburst;
  input s01_axi_arvalid;
  output s01_axi_arready;
  output [31:0]s01_axi_rdata;
  output [1:0]s01_axi_rresp;
  output s01_axi_rlast;
  output s01_axi_rvalid;
  input s01_axi_rready;
endmodule
