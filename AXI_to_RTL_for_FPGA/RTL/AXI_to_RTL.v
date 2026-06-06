
`timescale 1 ns / 1 ps

	module AXI_to_RTL #
	(
		// Users to add parameters here
		parameter integer M_SIZE     = 12,   // rows of A, rows of C
		parameter integer K_SIZE     = 12,   // cols of A = rows of B
		parameter integer N_SIZE     = 12,   // cols of B, cols of C
		parameter integer SA_SIZE    = 4,
		parameter integer DATA_WIDTH = 8,
		parameter integer OUT_WIDTH  = 16,   // spi_c_rdata element width
		parameter integer ACC_WIDTH  = 24,
		// Address widths — auto-computed from matrix dimensions (no manual update needed)
		parameter integer A_ADDR_W   = $clog2(M_SIZE*K_SIZE),
		parameter integer B_ADDR_W   = $clog2(K_SIZE*N_SIZE),
		parameter integer C_ADDR_W   = $clog2(M_SIZE*N_SIZE),
		// User parameters ends
		// Do not modify the parameters beyond this line


		// Parameters of Axi Slave Bus Interface S00_AXI
		parameter integer C_S00_AXI_ID_WIDTH	= 1,
		parameter integer C_S00_AXI_DATA_WIDTH	= 32,
		parameter integer C_S00_AXI_ADDR_WIDTH	= 6,
		parameter integer C_S00_AXI_AWUSER_WIDTH	= 0,
		parameter integer C_S00_AXI_ARUSER_WIDTH	= 0,
		parameter integer C_S00_AXI_WUSER_WIDTH	= 0,
		parameter integer C_S00_AXI_RUSER_WIDTH	= 0,
		parameter integer C_S00_AXI_BUSER_WIDTH	= 0
	)
	(
		// Users to add ports here
		output wire                      start_o,
		output wire [1:0]                act_type_o,
		output wire [1:0]                pool_type_o,
		output wire [4:0]                quant_shift_o,
		output wire [A_ADDR_W-1:0]       spi_a_waddr_o,
		output wire [DATA_WIDTH-1:0]     spi_a_wdata_o,
		output wire                      spi_a_we_o,
		output wire [B_ADDR_W-1:0]       spi_b_waddr_o,
		output wire [DATA_WIDTH-1:0]     spi_b_wdata_o,
		output wire                      spi_b_we_o,
		output wire [C_ADDR_W-1:0]       spi_c_raddr_o,
		input  wire                      done_i,
		input  wire                      norm_done_i,
		input  wire [OUT_WIDTH-1:0]      spi_c_rdata_i,
		// User ports ends
		// Do not modify the ports beyond this line


		// Ports of Axi Slave Bus Interface S00_AXI
		input wire  s00_axi_aclk,
		input wire  s00_axi_aresetn,
		input wire [C_S00_AXI_ID_WIDTH-1 : 0] s00_axi_awid,
		input wire [C_S00_AXI_ADDR_WIDTH-1 : 0] s00_axi_awaddr,
		input wire [7 : 0] s00_axi_awlen,
		input wire [2 : 0] s00_axi_awsize,
		input wire [1 : 0] s00_axi_awburst,
		input wire  s00_axi_awlock,
		input wire [3 : 0] s00_axi_awcache,
		input wire [2 : 0] s00_axi_awprot,
		input wire [3 : 0] s00_axi_awqos,
		input wire [3 : 0] s00_axi_awregion,
		input wire [C_S00_AXI_AWUSER_WIDTH-1 : 0] s00_axi_awuser,
		input wire  s00_axi_awvalid,
		output wire  s00_axi_awready,
		input wire [C_S00_AXI_DATA_WIDTH-1 : 0] s00_axi_wdata,
		input wire [(C_S00_AXI_DATA_WIDTH/8)-1 : 0] s00_axi_wstrb,
		input wire  s00_axi_wlast,
		input wire [C_S00_AXI_WUSER_WIDTH-1 : 0] s00_axi_wuser,
		input wire  s00_axi_wvalid,
		output wire  s00_axi_wready,
		output wire [C_S00_AXI_ID_WIDTH-1 : 0] s00_axi_bid,
		output wire [1 : 0] s00_axi_bresp,
		output wire [C_S00_AXI_BUSER_WIDTH-1 : 0] s00_axi_buser,
		output wire  s00_axi_bvalid,
		input wire  s00_axi_bready,
		input wire [C_S00_AXI_ID_WIDTH-1 : 0] s00_axi_arid,
		input wire [C_S00_AXI_ADDR_WIDTH-1 : 0] s00_axi_araddr,
		input wire [7 : 0] s00_axi_arlen,
		input wire [2 : 0] s00_axi_arsize,
		input wire [1 : 0] s00_axi_arburst,
		input wire  s00_axi_arlock,
		input wire [3 : 0] s00_axi_arcache,
		input wire [2 : 0] s00_axi_arprot,
		input wire [3 : 0] s00_axi_arqos,
		input wire [3 : 0] s00_axi_arregion,
		input wire [C_S00_AXI_ARUSER_WIDTH-1 : 0] s00_axi_aruser,
		input wire  s00_axi_arvalid,
		output wire  s00_axi_arready,
		output wire [C_S00_AXI_ID_WIDTH-1 : 0] s00_axi_rid,
		output wire [C_S00_AXI_DATA_WIDTH-1 : 0] s00_axi_rdata,
		output wire [1 : 0] s00_axi_rresp,
		output wire  s00_axi_rlast,
		output wire [C_S00_AXI_RUSER_WIDTH-1 : 0] s00_axi_ruser,
		output wire  s00_axi_rvalid,
		input wire  s00_axi_rready
	);
// Instantiation of Axi Bus Interface S00_AXI
	AXI_to_RTL_slave_full_v1_0_S00_AXI # (
		.M_SIZE(M_SIZE),
		.K_SIZE(K_SIZE),
		.N_SIZE(N_SIZE),
		.SA_SIZE(SA_SIZE),
		.DATA_WIDTH(DATA_WIDTH),
		.OUT_WIDTH(OUT_WIDTH),
		.ACC_WIDTH(ACC_WIDTH),
		.A_ADDR_W(A_ADDR_W),
		.B_ADDR_W(B_ADDR_W),
		.C_ADDR_W(C_ADDR_W),
		.C_S_AXI_ID_WIDTH(C_S00_AXI_ID_WIDTH),
		.C_S_AXI_DATA_WIDTH(C_S00_AXI_DATA_WIDTH),
		.C_S_AXI_ADDR_WIDTH(C_S00_AXI_ADDR_WIDTH),
		.C_S_AXI_AWUSER_WIDTH(C_S00_AXI_AWUSER_WIDTH),
		.C_S_AXI_ARUSER_WIDTH(C_S00_AXI_ARUSER_WIDTH),
		.C_S_AXI_WUSER_WIDTH(C_S00_AXI_WUSER_WIDTH),
		.C_S_AXI_RUSER_WIDTH(C_S00_AXI_RUSER_WIDTH),
		.C_S_AXI_BUSER_WIDTH(C_S00_AXI_BUSER_WIDTH)
	) AXI_to_RTL_slave_full_v1_0_S00_AXI_inst (
		.start_o(start_o),
		.act_type_o(act_type_o),
		.pool_type_o(pool_type_o),
		.quant_shift_o(quant_shift_o),
		.spi_a_waddr_o(spi_a_waddr_o),
		.spi_a_wdata_o(spi_a_wdata_o),
		.spi_a_we_o(spi_a_we_o),
		.spi_b_waddr_o(spi_b_waddr_o),
		.spi_b_wdata_o(spi_b_wdata_o),
		.spi_b_we_o(spi_b_we_o),
		.spi_c_raddr_o(spi_c_raddr_o),
		.done_i(done_i),
		.norm_done_i(norm_done_i),
		.spi_c_rdata_i(spi_c_rdata_i),
		.S_AXI_ACLK(s00_axi_aclk),
		.S_AXI_ARESETN(s00_axi_aresetn),
		.S_AXI_AWID(s00_axi_awid),
		.S_AXI_AWADDR(s00_axi_awaddr),
		.S_AXI_AWLEN(s00_axi_awlen),
		.S_AXI_AWSIZE(s00_axi_awsize),
		.S_AXI_AWBURST(s00_axi_awburst),
		.S_AXI_AWLOCK(s00_axi_awlock),
		.S_AXI_AWCACHE(s00_axi_awcache),
		.S_AXI_AWPROT(s00_axi_awprot),
		.S_AXI_AWQOS(s00_axi_awqos),
		.S_AXI_AWREGION(s00_axi_awregion),
		.S_AXI_AWUSER(s00_axi_awuser),
		.S_AXI_AWVALID(s00_axi_awvalid),
		.S_AXI_AWREADY(s00_axi_awready),
		.S_AXI_WDATA(s00_axi_wdata),
		.S_AXI_WSTRB(s00_axi_wstrb),
		.S_AXI_WLAST(s00_axi_wlast),
		.S_AXI_WUSER(s00_axi_wuser),
		.S_AXI_WVALID(s00_axi_wvalid),
		.S_AXI_WREADY(s00_axi_wready),
		.S_AXI_BID(s00_axi_bid),
		.S_AXI_BRESP(s00_axi_bresp),
		.S_AXI_BUSER(s00_axi_buser),
		.S_AXI_BVALID(s00_axi_bvalid),
		.S_AXI_BREADY(s00_axi_bready),
		.S_AXI_ARID(s00_axi_arid),
		.S_AXI_ARADDR(s00_axi_araddr),
		.S_AXI_ARLEN(s00_axi_arlen),
		.S_AXI_ARSIZE(s00_axi_arsize),
		.S_AXI_ARBURST(s00_axi_arburst),
		.S_AXI_ARLOCK(s00_axi_arlock),
		.S_AXI_ARCACHE(s00_axi_arcache),
		.S_AXI_ARPROT(s00_axi_arprot),
		.S_AXI_ARQOS(s00_axi_arqos),
		.S_AXI_ARREGION(s00_axi_arregion),
		.S_AXI_ARUSER(s00_axi_aruser),
		.S_AXI_ARVALID(s00_axi_arvalid),
		.S_AXI_ARREADY(s00_axi_arready),
		.S_AXI_RID(s00_axi_rid),
		.S_AXI_RDATA(s00_axi_rdata),
		.S_AXI_RRESP(s00_axi_rresp),
		.S_AXI_RLAST(s00_axi_rlast),
		.S_AXI_RUSER(s00_axi_ruser),
		.S_AXI_RVALID(s00_axi_rvalid),
		.S_AXI_RREADY(s00_axi_rready)
	);

	// Add user logic here

	// User logic ends

	endmodule
